#----- ----- ----- ----- ----- ----- ----- ----
# BarryBot5 client for COMP28512 Mobile Systems
# Originally by Andrew Leeming 2014
# Modified by Danny Wood & Robert James 25/3/2017
# Thanks to Igor Wodiany for his corrections
#----- ----- ----- ----- ----- ----- ----- ----
from socket import *
import select
import threading
import time
import datetime
import re
import traceback
import sys
import random
import binascii

TEXT_PIECE = '''The University of Manchester is a large research university situated in the city of Manchester, England. Manchester University - as it is commonly known - is a public university formed in 2004 by the merger of the University of Manchester Institute of Science and Technology (est. 1824) and the Victoria University of Manchester (est. 1851). Manchester is a member of the worldwide Universities Research Association group, the Russell Group of British research universities and the N8 Group. The University of Manchester has been a "red brick university" since 1880 when Victoria University gained its royal charter.'''


REPEAT_MSG = "Sent by BarryBot, School of Computer Science, The University of Manchester"
# Fixed key for testing:
KEY = "1<AK8JNZBCHXUHCV1A?BYSE8PQW485M=XIK84MATON2NYYNU9KLWHBQO=PWPF<TE=L5SY601I1"
KEY_LEN = len(REPEAT_MSG)


class BarryBot(object):

    def __init__(self):
        self.host = '127.0.0.1'  # Default if no ip given as arg
        self.buff_size = 4096
        self.server_port = 9999  # Default if no port given as arg
        self.signature_prob = 0.2  # Probability of signature instead of a fragment of text
        self.socklst = []
        self.svr = socket(AF_INET, SOCK_STREAM)
        self.svr.connect((self.host, self.server_port))
        self.socklst.append(self.svr)

    def main_loop(self):

        if len(sys.argv) == 2:
            self.host = sys.argv[1]

        # Set up socket connections

        # This would be used if you wanted a random key every time you run barryBot
        KEY = genRandStr(KEY_LEN)
        # else KEY is statically defined
        # print "KEY is ",KEY

        # Register barrybot
        self.svr.send("REGISTER BarryBot5")

        try:
            while True:
                ready_socks, _, _ = select.select([self.svr], [], [])
                for sock in ready_socks:
                    # Grab the ip and port values of this socket (we do not know which one it is yet)
                    #iip,pport = sock.getpeername()#
                    data = sock.recv(self.buff_size)
                    message_type = data.split(" ", 1)[0]
                    # If Socket closed
                    if not data:
                        sock.close()
                        print "Socket connection lost - Exiting BarryBot"
                        sys.exit()

                    print "SERVER PORT :", data
                    msg2_regex = re.compile("[0-5]MSG")
                    print("Message Type: %s" % message_type)

                    if message_type == "INVITE":
                        self.accept(sock, data)
                    elif message_type == "MSG":  # Keeping MSG for debugging
                        self.msg(sock, data)

                    elif msg2_regex.match(message_type):
                        print("Code gets here")
                        kind, sender, content = data.split(" ", 2)
                        if "ENCRYPT" in content.upper() and len(content) <= 9:
                            self.encrypt(sock, sender)

                        else:
                            data = "BarryBot5 (via channel): " + data
                            sock.send("0MSG " + sender + " " + content + "\n")

        except KeyboardInterrupt:
            print "Caught KeyboardInterrupt"
            print "Closing sockets"
            self.close_sockets()

    def close_sockets(self):
        for sk in self.socklst:
            sk.close()


    def accept(self, sock, data):
        print "Accepting invite :", data
        sock.send("ACCEPT " + data[7:]);

    def msg(self, sock, data):
        w = data[4:].split(' ', 1)
        print "Msg on server port :", data
        msg = \
            re.sub("[Bb]arry([Bb]ot5?)?",
                   w[0], w[1])
        # +w[1] );
        sock.send("MSG " + w[0] + " I AM A ROBOT : " + msg);

    def encrypt(self, sock, sender):
        """
        Encrypts either the signature with probability self.signature_prob or
        part of the message with probability (1 - self.signature_prob)
        """
        print("encrypt reached")
        if random.random() < self.signature_prob: 
            text = REPEAT_MSG
        else:
            # Rest of data discarded now, grab random text
            text = getRandText()
        # Encrypt it
        print "Random text is :", text
        en = encrypt(text)
        print "Encrypted version is :", en

        # For the lab, encode into ascii-binary
        asciibin = str2bin(en)
        asciibin = padLeftZeros(asciibin[2:], 8)
        # make sure bin is multiple of 8bits
        print "ascii version is :", asciibin
        sock.send("0MSG " + sender + " " + asciibin + "\n")

def genRandStr(size):
    '''
    Generate a random string of 8-bit ASCII chars
    '''
    gen = ""
    for i in xrange(size):
        gen = gen + chr(random.randint(48, 90))
    # end for
    return gen


def sxor(s1, s2):
    xorstr = ""
    # Strings s1 & s2 should contain '0' and '1' chars only
    for a, b in zip(s1, s2):
        xorstr = xorstr + str(int(a) ^ int(b))
    # end for
    return xorstr


def str2bin(s):
    return bin(int(binascii.hexlify(s), 16))


def bin2str(b):
    # Convert binary b to string form ????
    return binascii.unhexlify('%x' % int(b, 2))
# --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---
# stackoverflow/questions/7396849/convert-binary-to-ascii-&-vice-versa
# --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---


def encrypt(s):
    '''
    Encrypt a string 's' using random text array KEY.
    '''
    cipherstr = ""
    # s and KEY should be ASCII strings of same length
    if len(s) != len(KEY):
        print "ERROR in encrypt: strings s & KEY not of same length"
    for chars in zip(s, KEY):  # chars is 2 element list
        c = chr(ord(chars[0]) ^ ord(chars[1]))
        cipherstr = cipherstr + c
    return cipherstr


def padLeftZeros(string, multiple):
    '''
    Since 0's on the LHS are chopped off, stick them back in
    since we are treating s as a string not a number
    '''
    while len(string) % multiple != 0:
        string = '0' + string
    return s

def getRandText():
    starti = random.randint(0, len(TEXT_PIECE) - KEY_LEN)
    return TEXT_PIECE[starti:starti + KEY_LEN]
# end of getRandText function

if __name__ == '__main__':
    BarryBot().main_loop()

