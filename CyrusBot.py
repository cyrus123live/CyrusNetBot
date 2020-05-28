import os
import sys
import argparse
import time
import signal
import math
import random

# include the netbot src directory in sys.path so we can import modules from it.
robotpath = os.path.dirname(os.path.abspath(__file__))
srcpath = os.path.join(os.path.dirname(robotpath),"src")
sys.path.insert(0,srcpath)

from netbots_log import log
from netbots_log import setLogLevel
import netbots_ipc as nbipc
import netbots_math as nbmath

robotName = "Cyrus_Bot"

def reverseDirection(direction, wall):

    if wall == "left" or wall == "right":
        if direction == math.pi/2:
            direction = math.pi * 3/2
        else:
            direction = math.pi/2
    elif wall == "up" or wall == "down":
        if direction == math.pi:
            direction = 0
        else:
            direction = math.pi

    return direction

def findSpeed(direction, startingDirection):
    getLocationReply = botSocket.sendRecvMessage({'type': 'getLocationRequest'})
    x = getLocationReply['x']
    y = getLocationReply['y']

    # if we are gonna hit a wall, slow down to 10% speed, else go full speed to avoid bullets
    if (x <= 100 and direction == math.pi) or (x >= 900 and direction == 0) or (y <= 100 and direction == math.pi * 3/2) or (y >= 900 and direction == math.pi/2):
        if startingDirection:
            return 10
        else:
            return 0
    else:
        return 50

def play(botSocket, srvConf):
    gameNumber = 0  # The last game number bot got from the server (0 == no game has been started)

    while True:
        try:
            # Get information to determine if bot is alive (health > 0) and if a new game has started.
            getInfoReply = botSocket.sendRecvMessage({'type': 'getInfoRequest'})
        except nbipc.NetBotSocketException as e:
            # We are always allowed to make getInfoRequests, even if our health == 0. Something serious has gone wrong.
            log(str(e), "FAILURE")
            log("Is netbot server still running?")
            quit()

        if getInfoReply['health'] == 0:
            # we are dead, there is nothing we can do until we are alive again.
            continue

        if getInfoReply['gameNumber'] != gameNumber:
            # A new game has started. Record new gameNumber and reset any variables back to their initial state
            gameNumber = getInfoReply['gameNumber']
            log("Game " + str(gameNumber) + " has started. Points so far = " + str(getInfoReply['points']))

            maxSpeed = 70
            reversing = False
            scanCounter = 0
            defensiveScan = False
            counter = 0
            direction = 0
            speed = 50
            startingDirection = True
            wall = ""
            currentMode = "scan"
            scanSlices = 32
            nextScanSlice = 0
            scanSliceWidth = math.pi * 2 / scanSlices
            maxScanSlice = 0
            minScanSlice = 0

            getLocationReply = botSocket.sendRecvMessage({'type': 'getLocationRequest'})
            x = getLocationReply['x']
            y = getLocationReply['y']

            # run to nearest wall from starting location
            if x < 500 and y < 500:
                if x >= y:
                    direction = math.pi * 3/2
                    wall = "down"
                else:
                    direction = math.pi
                    wall = "left"
            elif x < 500 and y >= 500:
                if x >= 1000-y:
                    direction = math.pi/2
                    wall = "up"
                else:
                    direction = math.pi
                    wall = "left"
            elif x >= 500 and y < 500:
                if 1000-x <= y:
                    direction = 0
                    wall = "right"
                else:
                    direction = math.pi * 3/2
                    wall = "down"
            elif x >= 500 and y >= 500:
                if x >= y:
                    direction = 0
                    wall = "right"
                else:
                    direction  = math.pi/2
                    wall = "up"

        try:

            getLocationReply = botSocket.sendRecvMessage({'type': 'getLocationRequest'})
            x = getLocationReply['x']
            y = getLocationReply['y']
            getSpeedReply = botSocket.sendRecvMessage({'type': 'getSpeedRequest'})

            if getSpeedReply['currentSpeed'] == 0:

                if not(startingDirection):
                    direction = reverseDirection(direction, wall)
                if counter >= 1:
                    startingDirection = False

                # Turn in a new direction
                botSocket.sendRecvMessage({'type': 'setDirectionRequest', 'requestedDirection': direction})

                speed = maxSpeed

                # log some useful information.
                log("Requested to go " + str(direction/math.pi) + " pi radians at speed: " + str(speed), "INFO")
                botSocket.sendRecvMessage({'type': 'setSpeedRequest', 'requestedSpeed': speed})
                reversing = False

            elif not(reversing):

                if startingDirection:
                    if (x <= 100 and direction == math.pi) or (x >= 900 and direction == 0) or (y <= 100 and direction == math.pi * 3/2) or (y >= 900 and direction == math.pi/2):
                        speed = 10
                else:
                    if (x <= 200 and direction == math.pi) or (x >= 800 and direction == 0) or (y <= 200 and direction == math.pi * 3/2) or (y >= 800 and direction == math.pi/2):
                        speed = 0
                        reversing = True
                    else:
                        speed = maxSpeed

                botSocket.sendRecvMessage({'type': 'setSpeedRequest', 'requestedSpeed': speed})

            if not(startingDirection):
                if currentMode == "wait":
                    # find out if we already have a shell in the air. We need to wait for it to explode before
                    # we fire another shell. If we don't then the first shell will never explode!
                    getCanonReply = botSocket.sendRecvMessage({'type': 'getCanonRequest'})
                    if not getCanonReply['shellInProgress']:
                        # we are ready to shoot again!
                        currentMode = "scan"

                if currentMode == "scan":

                    defensiveScan = True if scanCounter % 5 == 0 else False

                    # defensive scan
                    if defensiveScan:
                        scanSliceTemp = nextScanSlice

                        scanRadStart = direction - math.pi/4
                        scanRadEnd = direction + math.pi/4

                        if scanRadStart < 0:
                            scanRadStart += math.pi*2
                        if scanRadEnd >= math.pi*2:
                            scanRadEnd -= math.pi*2

                    else:

                        scanSliceWidth = math.pi * 2 / scanSlices
                        scanRadStart = nextScanSlice * scanSliceWidth
                        scanRadEnd = min(scanRadStart + scanSliceWidth, math.pi * 2)

                    scanReply = botSocket.sendRecvMessage(
                        {'type': 'scanRequest', 'startRadians': scanRadStart, 'endRadians': scanRadEnd})

                    if defensiveScan:
                        nextScanSlice = scanSliceTemp - 1

                    # if we found an enemy robot with our scan
                    if scanReply['distance'] != 0:
                        if scanReply['distance'] >= 100:
                            # fire down the center of the slice we just scanned.
                            fireDirection = scanRadStart + scanSliceWidth / 2
                            botSocket.sendRecvMessage(
                                {'type': 'fireCanonRequest', 'direction': fireDirection, 'distance': scanReply['distance']})
                            # make sure don't try and shoot again until this shell has exploded.
                            currentMode = "wait"
                        if defensiveScan and scanReply['distance'] <= 200:
                            # if the scan shows that a bot is right in front of us, we want to reverse direction as to not get hit
                            log("there is a bot that scares us", "INFO")
                            reversing = True
                            speed = 0
                            botSocket.sendRecvMessage({'type': 'setSpeedRequest', 'requestedSpeed': speed})

                    else:
                        nextScanSlice += 1
                    if nextScanSlice == maxScanSlice:
                        nextScanSlice = minScanSlice
                    elif nextScanSlice == scanSlices:
                        nextScanSlice = 0
                    scanCounter += 1

            # initialize starting scan slice
            else:
                if wall == "up":
                    nextScanSlice = 16
                    minScanSlice = 16
                    maxScanSlice = 32
                elif wall == "left":
                    nextScanSlice = 24
                    minScanSlice = 24
                    maxScanSlice = 8
                elif wall == "down":
                    nextScanSlice = 0
                    minScanSlice = 0
                    maxScanSlice = 16
                elif wall == "right":
                    nextScanSlice = 8
                    minScanSlice = 8
                    maxScanSlice = 24

            counter += 1

        except nbipc.NetBotSocketException as e:
            # Consider this a warning here. It may simply be that a request returned
            # an Error reply because our health == 0 since we last checked. We can
            # continue until the next game starts.
            log(str(e), "WARNING")
            continue

##################################################################
# Standard stuff below.
##################################################################


def quit(signal=None, frame=None):
    global botSocket
    log(botSocket.getStats())
    log("Quiting", "INFO")
    exit()


def main():
    global botSocket  # This is global so quit() can print stats in botSocket
    global robotName

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-ip', metavar='My IP', dest='myIP', type=nbipc.argParseCheckIPFormat, nargs='?',
                        default='127.0.0.1', help='My IP Address')
    parser.add_argument('-p', metavar='My Port', dest='myPort', type=int, nargs='?',
                        default=20010, help='My port number')
    parser.add_argument('-sip', metavar='Server IP', dest='serverIP', type=nbipc.argParseCheckIPFormat, nargs='?',
                        default='127.0.0.1', help='Server IP Address')
    parser.add_argument('-sp', metavar='Server Port', dest='serverPort', type=int, nargs='?',
                        default=20000, help='Server port number')
    parser.add_argument('-debug', dest='debug', action='store_true',
                        default=False, help='Print DEBUG level log messages.')
    parser.add_argument('-verbose', dest='verbose', action='store_true',
                        default=False, help='Print VERBOSE level log messages. Note, -debug includes -verbose.')
    args = parser.parse_args()
    setLogLevel(args.debug, args.verbose)

    try:
        botSocket = nbipc.NetBotSocket(args.myIP, args.myPort, args.serverIP, args.serverPort)
        joinReply = botSocket.sendRecvMessage({'type': 'joinRequest', 'name': robotName}, retries=300, delay=1, delayMultiplier=1)
    except nbipc.NetBotSocketException as e:
        log("Is netbot server running at" + args.serverIP + ":" + str(args.serverPort) + "?")
        log(str(e), "FAILURE")
        quit()

    log("Join server was successful. We are ready to play!")

    # the server configuration tells us all about how big the arena is and other useful stuff.
    srvConf = joinReply['conf']
    log(str(srvConf), "VERBOSE")

    # Now we can play, but we may have to wait for a game to start.
    play(botSocket, srvConf)


if __name__ == "__main__":
    # execute only if run as a script
    signal.signal(signal.SIGINT, quit)
    main()
