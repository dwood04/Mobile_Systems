# Server for COMP28512 - MobileSystems and COMP61242 - Mobile Comunications labs.
# Contributions by: 
# Andrew Leeming
# Danny Wood
# Robert James
# Thanks to Igor Wodiany for his corrections
# 
# Multiple socket code modified from
# http://code.activestate.com/recipes/578247-basic-threaded-python-tcp-server/
####

from socket import *
import select
import random
import threading
import time
import datetime
import re
import traceback
import sys

BUFF = 4096  # Socket input buffer size (number of chars)
HOST = '127.0.0.1'  # Default if no ip given as arg
SERVER_PORT = 9999  # Default port of proxyserver
# CHANNEL_PORT = 9998  # Default port of channel simulator

# Channel types
CH_BENIGN = 0
CH_BIT1 = 1
CH_BIT2 = 2
CH_BURSTY = 3
CH_DROP1 = 4
CH_DROP2 = 5

# Here are all the error/packet loss probabilities for each channel type
CHANNEL_1_ERR = 0.001
CHANNEL_2_ERR = 0.01
CHANNEL_3_ERR = 0.02
CHANNEL_4_ERR = 0.05
CHANNEL_5_ERR = 0.2
MODE3_BURSTLEN = 20   # Length (number of bits) of each burst

# Server static messages
SVR_NOREG = "Registration required to do this"
SVR_SHUTDOWN = "INFO Server going down\n"
SVR_INVALID_CH = "Invalid channel type, assuming 0"
SVR_CH_SYNTAX_ERR = "Username and data required for message"
SVR_CMD_ERR = "Not a command"
SVR_CMD_ERR_DEBUG = "ERROR - Incorrect command given"
SVR_INFO_BYE = "INFO Goodbye\n"
SVR_REG_TWICE = "You have already registered"
SVR_REG_TAKEN = "Username already taken"
SVR_REG_EMPTY = "You must provide a username"
SVR_INVITE_UNKNOWN = "Username not online"
SVR_INVITE_DUP = "Already have connection with this person"
SVR_INVITE_CONN_REQ = "You do not have a connection with this person"
SVR_ACCEPT_EMPTY = "User to accept expected, non given"
SVR_ACCEPT_NULL_CONN = "Can only accept invites"
SVR_DECLINE_EMPTY = "User to DECLINE expected, non given."
SVR_DECLINE_NULL_CONN = "Can only DECLINE invites"
SVR_MSG_NULL_CONN = "You need to initiate a connection first"


# nternal datastructures that keep track of clients on the server
whoDB = {}  # Dictionary of who is online => username : {ip,port,socket}
inviteDB = {}  # Dictionary of who has invites pending (waiting for ACCEPT or DECLINE)
connectionDB = []  # List of sets (person-A,person-B) of established connections
threadsDB = []  # List of all threads, only needed for shuting down server nicely
threadsWho = {}  # Same as above but indexed to ip 

UNREG_UN = "[Unregistered]"

class ClientThread(threading.Thread):

    # ClientThread constructor
    def __init__(self, clientsock, addr=''):
        self.killed = False
        '''
        Each connection from a client creates a new thread. The constructor
        keeps a reference to both the control+simulated channel sockets.

        '''

        super(ClientThread, self).__init__()

        self.clientsock = clientsock
        self.addr = addr
        self.username = UNREG_UN

    def channel_simulator(self, typeid, data):
        """
        This is the code for the channel simulator. This simulates a wireless
        link between peer-to-peer clients and introduces errors depending on
        the typeid param supplied.

        typeid: type (exersise number/mode/index) of channel to use
        data: datagram to send over the channel

        returns a modified version of 'data' (depending on typeid)
        """

        newdata = bytearray(data)

        # Seed random number generator so we do not get same error seq
        random.seed(str(datetime.datetime.now()))

        # Benign (no errors)
        if isinstance(typeid, str):
            typeid = int(typeid)
        if typeid == CH_BENIGN:
            pass
        # Random error (low pr)
        elif typeid == CH_BIT1 or typeid == CH_BIT2:
            if typeid == CH_BIT1:
                bEP = CHANNEL_1_ERR
            else:
                bEP = CHANNEL_2_ERR

            # Per char
            for i in xrange(0, len(data)):
                if random.random() < bEP:
                    # Flips binary data or replaces char with '~' *messy hack*
                    if data[i] == "1":
                        newdata[i] = "0"
                    elif data[i] == "0":
                        newdata[i] = "1"  # appends 1
                    else:
                        pass  # No changes to any other chars
                # end if random

        #================================================================
        # Mod by Barry for Bursty errors
        #================================================================
        # Bursty errors
        elif typeid == CH_BURSTY:
            bEP = CHANNEL_3_ERR * random.random()
            # Set a value of bEP in range 0 to MODE3_MAX_BEP
            Nburst = 0  # Initialise burstlength counter
            for i in xrange(0, len(data)):
                if random.random() < bEP:
                    if data[i] == "1":
                        newdata[i] = "0"
                    elif data[i] == "0":
                        newdata[i] = "1"
                    else:
                        pass  # Dont change other chars
                Nburst = Nburst + 1
                if Nburst == MODE3_BURSTLEN:
                    bEP = CHANNEL_3_ERR * random.random()
                    # Change bit-error probability for next burst
                    Nburst = 0  # Restart burst-len counter

        # Lost packets (low pr)
        elif typeid == CH_DROP1:
            pLP = CHANNEL_4_ERR

            if random.random() < pLP:
                newdata = "0" * 20
            else:
                newdata = data
        # Lost packets (high pr)
        elif typeid == CH_DROP2:
            pLP = CHANNEL_5_ERR

            if random.random() < pLP:
                newdata = "0" * 20
            else:
                newdata = data

        # Error/ unknown channel type
        else:
            print "unknown channel type"

        # Return data with errors
        newdata = str(newdata)
        return newdata

    # End channel_simulator
    
    def out(self, msg):
        '''
        Server-side debugging print function
        '''
        ts = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
        print "[", ts, "] ", self.username, " : ", msg
    # End out

    def err(self, errmsg):
        '''
        Send the client an error packet
        '''
        self.clientsock.send("ERROR " + errmsg + "\n")
        # todo MSC want error codes here?
    # End err

    def regRequired(self):
        '''
        Simple check to see if client is currently registered a username.
        If not an error packet is sent
        '''
        if self.username == UNREG_UN:
            self.err(SVR_NOREG)
            return False
        else:
            return True
    # End regRequired

    def kill(self):
        try:
            self.clientsock.send(SVR_SHUTDOWN)
        except:
            pass
        print self, 'killed'
        self.killed = True
    # End kill

    def run(self):
        '''
        This is the 'main' part of the thread. This is run automatically
        when the thread is started
        '''
        # This is run per server connection thread
        self.out('New connection from:' + str(self.addr))

        # List of sockets currently listening to. 
        self.sockets = [self.clientsock]

        try:
            while not self.killed:
                # checks client and posisbly channel connection associated with this
                # thread
                ready_socks, _, _ = select.select(self.sockets, [], [])

                # Deal with whichever socket is ready
                if ready_socks:
                    for sock in ready_socks:
                        # Grab the ip and port values of this socket (we do not know which
                        # one it is yet)
                        iip, pport = sock.getsockname()

                        # Directory/SIP/Proxy server
                        if pport == SERVER_PORT:
                            # DW: Can it be any other port? 
                            data = sock.recv(BUFF)
                            # Socket closed
                            if not data:
                                sock.close()
                                socklst.remove(sock)
                            else:
                                self.process_command(data)

        except Exception as e:
            self.err("Critical error. Please see trace on server")
            print str(e)
            traceback.print_exc()
        # Client has disconnected by closing the socket
        self.disconnect()

    def process_command(self, data):
        data = data.rstrip()
        self.out(">> " + repr(self.addr) + " : " + repr(data))

        # Delegate to methods to handle the commands
        msg2_regex = re.compile("[0-5]MSG")
        if data[:8].upper() == "REGISTER":
            self.register(data[9:]);
        elif data[:1].upper() == "R":  # Short command for REGISTER because I'm lazy
            self.register(data[2:]);
        elif data[:3].upper() == "WHO":
            self.who()
        elif data[:10].upper() == "DISCONNECT":
            self.disconnect()
        elif data[:2].upper() == "DC":  # Short command for DISCONNECT because I'm lazy
            self.disconnect()
        elif data[:4].upper() == "DUMP":
            self.dump()
        elif data[:3].upper() == "MSG":  # MSG command for lab4 + lab5 debug
            w = data[4:].split(' ', 1)
            if w[0].upper() in ["BARRY", "BAR"]:
                w[0] = "BarryBot5"
            if len(w) == 2:
                self.msg(w[0], w[1])
            else:
                self.err("<msgto> <msgtext> required")
        elif data[:6].upper() == "INVITE":
            self.invite(data[7:]);
        elif data[:6].upper() == "ACCEPT":
            self.accept(data[7:]);
        elif data[:7].upper() == "DECLINE":
            self.decline(data[8:]);
        elif data[:3].upper() == "END":
            self.end(data[4:]);
        elif data == "DEBUG":
            self.register("Danny")
            self.invite("BarryBot5")
            time.sleep(1)
            self.msg2("2", "BarryBot5", "Hello")
            self.msg2("0", "BarryBot5", "Encrypt")
            time.sleep(1)
            self.who()
        elif msg2_regex.match(data[:4]):
            channel = data[0]
            w = data[5:].split(' ', 1)
            if w[0].upper() in ["BARRY", "BAR"]:
                w[0] = "BarryBot5"
            if len(w) == 2:
                self.msg2(data[0], w[0], w[1])
            else:
                self.err("<msgto> <msgtext> required")
        else:
            print data
            self.out(SVR_CMD_ERR_DEBUG)
            self.err(SVR_CMD_ERR)

    def disconnect(self):
        try:
            # Update online list (if registered)
            if self.username != UNREG_UN:
                if not whoDB.has_key(self.username):
                    return
                del whoDB[self.username]
                del inviteDB[self.username]

            # threadsDB.remove(self);
            threadsWho.pop(str(self.addr[0]) + ":" + str(self.addr[1]), None)
            # Close socket
            try:
                self.clientsock.send(SVR_INFO_BYE)
                self.clientsock.close()
            except:
                pass

            self.killed = True

            print self.addr, "- closed connection"  # log on console
        except:
            print "Strange exception happened again. Double disconnect????"
            traceback.print_exc()

    def register(self, data):
        # Do some basic checks first
        # Strip all whitespace
        data = re.sub(r'\s', '', data)

        # Client already registered
        if self.username != UNREG_UN:
            self.err(SVR_REG_TWICE)
            return
        # Name already exists?
        elif data in whoDB:
            self.err(SVR_REG_TAKEN)
            return
        # Only whitespace given as name
        elif data.rstrip() == "":
            self.err(SVR_REG_EMPTY)
            return

        self.clientsock.send("INFO Welcome " + data + "\n")

        # Add to online list and do some bookkeeping
        self.out("Registering " + data)
        self.username = data
        inviteDB[self.username] = []
        whoDB[self.username] = {'socket': self.clientsock,
                                'ip': self.addr[0], 'port': self.addr[1]}
        return

    def invite(self, invitee):
        # Check if user is registered
        if not self.regRequired():
            return

        # Check to see if invitee exists
        if invitee not in whoDB:
            self.err(SVR_INVITE_UNKNOWN)
            return

        # Check if there is already a channel open
        if set([self.username, invitee]) in connectionDB:
            self.err(SVR_INVITE_DUP)
            return

        # Send invite
        rec = whoDB[invitee]
        self.out("Inviting " + invitee + " to chat with " + self.username)
        rec['socket'].send("INVITE " + self.username + "\n")
        inviteDB[invitee].append(self.username)

        return

    def end(self, endee):
        # Check if user is registered
        if not self.regRequired():
            return

        # Check if there is already a channel open
        if set([self.username, endee]) not in connectionDB:
            self.err(SVR_INVITE_CONN_REQ)
            return

        # Send end notice
        rec = whoDB[endee]
        self.out("Ending connection between " + endee + " and " + self.username)
        rec['socket'].send("END " + self.username + "\n")
        connectionDB.remove(set([endee, self.username]))

        return

    def accept(self, acceptwho=''):
        # Check if user is registered
        if not self.regRequired():
            return
        if acceptwho == "":
            self.err(SVR_ACCEPT_EMPTY)
            return

        # Check if person you are accepting to chat with has sent an invite
        if acceptwho not in inviteDB[self.username]:
            self.err(SVR_ACCEPT_NULL_CONN)
            return

        connectionDB.append(set([acceptwho, self.username]))
        whoDB[acceptwho]['socket'].send("ACCEPT " + self.username + "\n")

        # Remove invite after accepting
        inviteDB[self.username].remove(acceptwho)

        self.clientsock.send("INFO Connection setup\n")
        self.out("Connection setup between " + acceptwho + " and " + self.username)

        return

    def decline(self, declinewho=''):
        # Check if user is registered
        if not self.regRequired():
            return
        if declinewho == "":
            self.err(SVR_DECLINE_EMPTY)
            return

        # Check if person you are decline to chat with has sent an invite
        if declinewho not in inviteDB[self.username]:
            self.err(SVR_DECLINE_NULL_CONN)
            return

        # Remove invite after declining
        inviteDB[self.username].remove(declinewho)
        whoDB[declinewho]['socket'].send("DECLINE " + self.username + "\n")

        self.out("Connection declined between " + declinewho + " and " + self.username)
        self.clientsock.send("INFO Connection declined\n")

        return

    # Send a message via proxy server (Lab4)
    def msg(self, msgwho, text):
        # Check if user is registered
        if not self.regRequired():
            return

        # Check if user has a connection with msgwho
        if set([self.username, msgwho]) in connectionDB:
            # Go ahead and send message
            whoDB[msgwho]['socket'].send("MSG " + self.username + " " + text + "\n")
            self.out("MSG TO " + msgwho + ": " + text)
        else:
            self.err(SVR_MSG_NULL_CONN)

    # Send a message via channel simulator (Lab5)
    def msg2(self, typeid, msgwho, text):
        # Check if user is registered
        if not self.regRequired():
            return

        print ">>", self.username, "::", msgwho
        print text
        print connectionDB
        print("typid is: %s" % typeid)
        # Check if user has a connection with msgwho
        if set([self.username, msgwho]) in connectionDB:
            # Run message via channel simulator
            print "Username is in connectiondb"
            mangledMsg = self.channel_simulator(typeid, text)
            print "Mangled Message: %s" % mangledMsg

            # Go ahead and send message
            if mangledMsg != "0" * 20:  # Droped packet is a string of 20 zeros
                # If talking to barrybot, give 'from' so it can respond
                if msgwho == "BarryBot5":
                    print "This is running!"
                    mangledMsg = typeid + "MSG " + self.username + " " + mangledMsg
                    print mangledMsg

                print "Message is going to %s" % msgwho
                whoDB[msgwho]['socket'].send(mangledMsg + "\n")
                self.out("MSG2(" + typeid + ") " + msgwho + " " + mangledMsg)
            else:
                #packet is dropped
                self.out("Dropping packet")
        else:
            self.err(SVR_MSG_NULL_CONN)

    def who(self):
        # Check if user is registered
        if not self.regRequired():
            return

        self.out("Online now: " + printWhoDB())
        self.clientsock.send("WHO " + str(whoDB.keys()) + "\n")
        return

    def dump(self):
        self.out("WHO :" + str(whoDB))
        self.out("INVITE :" + str(inviteDB))
        self.out("CONN :" + str(connectionDB))
        self.out("THREADS :" + str(threadsWho.keys()))

def printWhoDB():
    return str(whoDB.keys())

def removeConnections(user):
    for s in connectionDB:
        if user in s:
            connectionDB.remove(s)


if __name__ == '__main__':

    # Only argument is to set IP address to something else
    if len(sys.argv) == 2:
        HOST = sys.argv[1]

    # Set up main server socket (this is always TCP?)
    ADDR = (HOST, SERVER_PORT)
    serversock = socket(AF_INET, SOCK_STREAM)
    serversock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    serversock.bind(ADDR)
    serversock.listen(5)
    socklst = [serversock]

    print 'waiting for connection... Server listening on ', HOST, ":", SERVER_PORT
    # Listen for new client connections
    try:
        while 1:
            # Listen to all sockets
            ready_socks, _, _ = select.select(socklst, [], [])
            for sock in ready_socks:
                # Grab the ip and port values of this socket (we do not know which one it
                # is yet)
                iip, pport = sock.getsockname()

                if pport == SERVER_PORT:  # and not unconnected_count > 1:
                    clientsock, addr = sock.accept()
                    # clientsock.setblocking(0)
                    t = ClientThread(clientsock, addr=addr)
                    t.setDaemon(True)
                    threadsWho[str(addr[0]) + ":" + str(addr[1])] = t
                    threadsDB.append(t)
                    t.start()

    except KeyboardInterrupt:
        print "Catching keyboard interrupt, ending all connections"
        for t in threadsWho.keys():
            threadsWho[t].kill()
            threadsWho[t].clientsock.close()

    except Exception as e:
        print "Main loop error"
        traceback.print_exc()
    # end main
