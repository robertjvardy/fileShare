#!/usr/bin/python3
# ==============================================================================
# description     :This is node on the peer to peer file share system
# usage           :python Skeleton.py trackerIP trackerPort
# python_version  :3.5
# Authors         :Robert Vardy
# ==============================================================================

import socket
import sys
import threading
import json
import time
import os
import ssl
import os.path
import glob
import json
import optparse
import re


def validate_ip(s):
    """
    Validate the IP address of the correct format
    Arguments:
    s -- dot decimal IP address in string
    Returns:
    True if valid; False otherwise
    """
    a = s.split('.')
    if len(a) != 4:
        return False
    for x in a:
        if not x.isdigit():
            return False
        i = int(x)
        if i < 0 or i > 255:
            return False
    return True


def validate_port(x):
    """Validate the port number is in range [0,2^16 -1 ]
    Arguments:
    x -- port number
    Returns:
    True if valid; False, otherwise
    """
    if not x.isdigit():
        return False
    i = int(x)
    if i < 0 or i > 65535:
        return False
    return True


def get_file_info():
    """ Get file info in the local directory (subdirectories are ignored)
    Return: a JSON array of {'name':file,'mtime':mtime}
    i.e, [{'name':file,'mtime':mtime},{'name':file,'mtime':mtime},...]
    """
    file_arr = [f for f in os.listdir('.') if os.path.isfile(f)]
    file_arr = list(filter(lambda x: not re.match(
        '^.*(\.so|.py|\.dll)$', x), file_arr))
    file_arr = list(
        map(lambda x: {'name': x, 'mtime': int(os.path.getmtime(x))}, file_arr))

    return file_arr


def get_file_from_peer(fileName, fileData, BUFFER_SIZE):
    """ Creates a socket and requests a given file from a peer
        given an object of the form {filename:{ip: string, port: int, mtime: int}
    """
    peerHost = fileData["ip"]
    peerPort = fileData["port"]

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(180)
    client.connect((peerHost, peerPort))

    client.sendall(bytes(fileName, "utf-8"))

    return client.recv(BUFFER_SIZE)


def check_port_available(check_port):
    """Check if a port is available
    Arguments:
    check_port -- port number
    Returns:
    True if valid; False otherwise
    """
    if str(check_port) in os.popen("netstat -na").read():
        return False
    return True


def get_next_available_port(initial_port):
    """Get the next available port by searching from initial_port to 2^16 - 1
       Hint: You can call the check_port_avaliable() function
             Return the port if found an available port
             Otherwise consider next port number
    Arguments:
    initial_port -- the first port to check

    Return:
    port found to be available; False if no port is available.
    """
    maxPort = 2**16
    for x in range(initial_port, maxPort):
        if check_port_available(x):
            return x
    return False


class FileSynchronizer(threading.Thread):

    def __init__(self, trackerhost, trackerport, port, host='0.0.0.0'):

        threading.Thread.__init__(self)
        # Port for serving file requests
        self.port = port
        self.host = host

        # Tracker IP/hostname and port
        self.trackerhost = trackerhost
        self.trackerport = trackerport

        self.BUFFER_SIZE = 8192

        #   to communicate with the tracker
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.settimeout(180)

        # Store the message to be sent to the tracker.
        self.msg = bytes(json.dumps(
            {"port": self.port, "files": get_file_info()}), 'utf-8')

        # Create a TCP socket to serve file requests from peers.
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.server.bind((self.host, self.port))
        except socket.error:
            print(('Bind failed %s' % (socket.error)))
            sys.exit()
        self.server.listen(10)

    # Not currently used. Ensure sockets are closed on disconnect
    def exit(self):
        self.server.close()

    # Handle file request from a peer(i.e., send the file content to peers)
    def process_message(self, conn, addr):
        '''
        Arguments:
        self -- self object
        conn -- socket object for an accepted connection from a peer
        addr -- address bound to the socket of the accepted connection
        '''
        conn.settimeout(180)
        print("Connected with peer ", addr[0], ":", str(addr[1]))

        # Step 1. read the file name contained in the request through conn
        fileName = conn.recv(self.BUFFER_SIZE)

        # Step 2. read content of that file(assumming binary file <4MB), you can open with 'rb'
        f = open(fileName, "rb")

        # Step 3. send the content back to the requester through conn
        conn.sendall(f.read())

        # Step 4. close conn when you are done.
        f.close()
        conn.close()

    def run(self):
        self.client.connect((self.trackerhost, self.trackerport))
        t = threading.Timer(2, self.sync)
        t.start()
        print(('Waiting for connections on port %s' % (self.port)))
        while True:
            conn, addr = self.server.accept()
            threading.Thread(target=self.process_message,
                             args=(conn, addr)).start()

    # Send Init or KeepAlive message to tracker, handle directory response message
    # and  request files from peers
    def sync(self):
        print(('connect to:'+self.trackerhost, self.trackerport))
        # Step 1. send Init msg to tracker
        self.client.sendall(self.msg)

        # Step 2. now receive a directory response message from tracker
        directory_response_message = json.loads(
            self.client.recv(self.BUFFER_SIZE))
        # print('received from tracker:', directory_response_message)

        # Step 3. parse the directory response message. If it contains new or
        # more up-to-date files, request the files from the respective peers.
        # NOTE: compare the modified time of the files in the message and
        # that of local files of the same name.

        local_files = get_file_info()
        local_file_names = list(map(lambda x: x["name"], get_file_info()))

        remote_files = directory_response_message.keys()

        def find_mod_time_by_local_file_by_name(fileName):
            for lfile in local_files:
                if lfile["name"] == fileName:
                    return lfile["mtime"]
            return

        for remote_file in remote_files:
            if remote_file in local_file_names:
                if directory_response_message[remote_file]["mtime"] > find_mod_time_by_local_file_by_name(remote_file):
                    print("Outdated File: lname", remote_file)
                    file_data = get_file_from_peer(
                        remote_file, directory_response_message[remote_file], self.BUFFER_SIZE)
                    print(file_data)
            else:
                print("New File: ", remote_file)
                file_data = get_file_from_peer(
                    remote_file, directory_response_message[remote_file], self.BUFFER_SIZE)
                print(file_data)

        #      d. finally, write the file content to disk with the file name, use os.utime
        #         to set the mtime

        # Step 4. construct and send the KeepAlive message
        self.msg = bytes(json.dumps({"port": self.port}), 'utf-8')

        # Step 5. start timer
        t = threading.Timer(5, self.sync)
        t.start()


if __name__ == '__main__':
    # parse command line arguments
    parser = optparse.OptionParser(usage="%prog ServerIP ServerPort")
    options, args = parser.parse_args()
    if len(args) < 1:
        parser.error("No ServerIP and ServerPort")
    elif len(args) < 2:
        parser.error("No  ServerIP or ServerPort")
    else:
        if validate_ip(args[0]) and validate_port(args[1]):
            tracker_ip = args[0]
            tracker_port = int(args[1])

        else:
            parser.error("Invalid ServerIP or ServerPort")
    # get free port
    synchronizer_port = get_next_available_port(8000)
    synchronizer_thread = FileSynchronizer(
        tracker_ip, tracker_port, synchronizer_port)
    synchronizer_thread.start()
