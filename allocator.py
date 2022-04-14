#!/usr/bin/env python3
"""Allocator class."""
from atta_caseII import decider_thread
from setup import *


class Allocator:

    def __init__(self):
        self.tasks = {}
        self.state = {
            "shutdown": False,
            'decider_lock': threading.Lock(),
            'decider_pending': True,
            'decision': -1,
            'outcome': False,
            'taskNumber': -1,
        }

        self.state['decider_cv'] = threading.Condition(
            lock=self.state['decider_lock']
        )

        self.messageHandlers = {
            "boot": self.bootDecider,
            "kill": self.killDecider,
            "startTask": self.startTask,
            "endTask": self.endTask,
        }

        #signal.signal(signal.SIGINT, self.onSIGINT)

        listener = threading.Thread(target=self.listenerThread)
        listener.start()

        self.state['threads'] = [
            listener,
        ]

    """
    def onSIGINT(self, a, b):
        # Set shutdown flag and notify all waiting threads
        self.state['decider_lock'].acquire()
        self.state["shutdown"] = True
        self.state['decider_cv'].notify_all()
        self.state['decider_lock'].release()

        print('\nAllocator exited normally.')
    """

    def resetState(self):
        self.state['shutdown'] = False
        self.state['decider_pending'] = True
        self.state['decision'] = -1
        self.state['outcome'] = False
        self.state['taskNumber'] = -1


    def bootDecider(self, _):
        self.state['decider_lock'].acquire()
        print("Starting decider.")
        self.resetState()

        decider = threading.Thread(
            target=decider_thread, 
            args=(self.state,)
        )
        self.state['threads'].append(decider)

        self.state['decider_lock'].release()
        decider.start()
    

    def killDecider(self, _):
        self.state['decider_lock'].acquire()
        print("Acquisition success.")
        self.state["shutdown"] = True
        self.state['decider_cv'].notify_all()
        self.state['decider_lock'].release()


    def listenerThread(self):
        # Create an INET, DGRAM socket, this is UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Bind the UDP socket to the server 
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("localhost", 8001))
        sock.settimeout(1)

        # Receive incoming UDP messages
        while True: #not self.state["shutdown"]:
            try:
                message_bytes = sock.recv(4096)
            except socket.timeout:
                continue
            message_str = message_bytes.decode("utf-8")
            message = json.loads(message_str)
            self.handleMessage(message)
    

    def sendMessage(self, message):
        print("Sending Message:", message)

        # Create an INET, DGRAM socket, this is UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Connect to the UDP socket on server
        sock.connect(("localhost", 8002))

        # Send message
        sock.sendall(message.encode('utf-8'))
        sock.close()

    
    def handleMessage(self, message):
        print("Received Message:", message)

        if 'messageType' in message:
            handler = self.messageHandlers[message['messageType']]
            if handler is not None:
                handler(message)


    def startTask(self, message):
        print("Started task.")

        # NOTE:
        # (0) Wait for decider_thread to finish its main loop
        self.state['decider_lock'].acquire()
        while self.state['taskNumber'] != -1 or self.state['shutdown']:
            if self.state['shutdown']:
                return
            self.state['decider_cv'].wait()

        # NOTE:
        # (1) Initialize task data in shared state
        self.state['decision'] = -1
        self.state['decider_pending'] = False
        self.state['taskNumber'] = message['taskNumber']

        # NOTE:
        # (2) Release lock to allow decider_thread to execute 1st half of its main loop
        self.state['decider_cv'].notify_all()
        self.state['decider_lock'].release()
        
        # NOTE:
        # (3) Wait for decider_thread to make a decision
        self.state['decider_lock'].acquire()
        while not self.state['decider_pending'] or self.state['shutdown']:
            if self.state['shutdown']:
                return
            self.state['decider_cv'].wait()

        # NOTE:
        # (4) Obtain decision from shared state
        decisionMessage = self.getDecisionMessage()
        self.state['decider_lock'].release()

        # NOTE:
        # (5) Relay decision back to simluation
        self.sendMessage(decisionMessage)


    def getDecisionMessage(self):
        substrings = [
            '1' if self.state['decision'] else '0',
            str(self.state['task'][0]),
            str(self.state['task'][1])
        ]
        return ','.join(substrings)


    def endTask(self, message):
        # *** INSERT MECHANISM TO PREVENT MULTIPLE TASKS from executing concurrently ***

        # NOTE:
        # (1) Update task data in shared state
        self.state['decider_lock'].acquire()        
        self.state['outcome'] = message['outcome']
        self.state['decider_pending'] = False

        # NOTE:
        # (2) Release lock to allow decider_thread to execute 2nd half of its main loop
        self.state['decider_cv'].notify_all()
        self.state['decider_lock'].release()

        print("Ended task.")
    
