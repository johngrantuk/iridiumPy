#!/usr/bin/env python
""" Main RockBLOCK Iridium functions. """
import cgi, cgitb, time
import serial
import Globals
import logging, logging.handlers, traceback
import zmq
from datetime import datetime

DEBUG = False
ZmqSock = None

my_logger = logging.getLogger('IridiumLogger')
my_logger.setLevel(logging.DEBUG)
handler = logging.handlers.RotatingFileHandler(Globals.IridiumLog, maxBytes=1000000, backupCount=2)
my_logger.addHandler(handler)

def Log(Message):
    Message = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S:%f')[:-3] + "," + Message

    if DEBUG:
        print Message

    my_logger.debug(Message)

    if ZmqSock:
        ZmqSock.send_multipart([b"IridiumLog", Message])                                    # Outgoing ZMQ data.

def SetZmqSock(Socket):
    global ZmqSock
    ZmqSock = Socket

def OpenSerial(Port, Baud):
    serialPort = serial.Serial(port=Port,\
                               baudrate=Baud,\
                               parity=serial.PARITY_NONE,\
                               stopbits=serial.STOPBITS_ONE,\
                               bytesize=serial.EIGHTBITS,\
                               rtscts=True,\
                               timeout=60)

    return serialPort

def StartAutoRegister(serialPort):
    """ Set the Transceivers automatic SBD Network Registration mode. When Automatic SBD Network Registration is enabled, mode 1 or 2, the Transceiver monitors
    its current location and triggers an Automatic SBD Network Registration when it determines that the Transceiver has moved sufficiently far away from its last registered location."""
    Log("StartAutoRegister()")

    Log("Setting Register to Auto.")

    if not WriteAndCheck(serialPort, "AT+SBDAREG=1\r", "OK", 30):
        Log("Issue setting registration mode.")
        return False

    Log("OK.")
    return True

def StartReporting(serialPort):
    """ Enable indicator event reporting; buffer the most recent +CIEV unsolicited result code for each indicator when the data port is reserved (e.g. in SBD data mode) and flush them to
    the DTE after reservation; otherwise forward them directly to the DTE."""
    Log("StartReporting()")

    if not WriteAndCheck(serialPort, "AT+CIER=1,0,1\r", "OK", 40):
        Log("Issue Starting Reporting.")
        return False

    Log("Reporting Started.")
    return True

def EnableRing(serialPort):
    """ Enable the ISU to listen for SBD Ring Alerts. When SBD Ring Alert indication is enabled, the 9602 asserts the RI line and issues the unsolicited result
    code SBDRING when an SBD Ring Alert is received. """
                                                                                # Enables Ring message to indicate there's a message to read.
    Log("EnableRing()")

    if not WriteAndCheck(serialPort, "AT+SBDMTA=1\r", "OK", 30):
        Log("Issue enabling ring notifications.")
        return False

    Log("OK.")
    return True

def WaitForSigStr(serialPort, MinSigStr, Timeout):
    """ Checks receive signal strength for specified time returning true when above min level or false when timeout."""

    signalStr = 0

    timeout = time.time() + Timeout                                     # Set the timeout time

    while time.time() < timeout:                                        # Run the loop till the time out is reached or the ExpectedReply is found with an end of line.

        signalStr = CheckSignalStrength(serialPort)

        #if signalStr == None:
        #    Log("Not getting a signal strength from unit.")
        #    return

        if signalStr > MinSigStr:
            return True
        else:
            Log("Signal Strength Too Weak")
            time.sleep(3)

    Log("WaitForSigStr() Timed Out.")
    return False

def CheckSignalStrength(serialPort):
    """ Execution command returns the received signal strength indication <rssi> from the 9602.Each number represents about 2 dB improvement in link margin over the previous value. A
    reading of 0 is at or below the minimum receiver sensitivity level. A reading of 1 indicates about 2 db of link margin. A reading of 5 indicates 10 dB or more link margin."""

    Log("CheckSignalStrength()")

    reply = WriteAndReceive(serialPort, "AT+CSQ\r", "+CSQ:", '\r', 40)

    if reply is not None:
        index = reply.index("+CSQ:") + 5
        Log("Strength: " + reply[index])
        return int(reply[index])
    else:
        return None

def WriteAndReceive(serialPort, WriteCommand, Response, EOL, Timeout):
    """ Sends a message, reads to specified response is detected and EOL then returns read message."""

    try:
        Log("Sending Command: " + WriteCommand)

        SerialWrite(serialPort, WriteCommand)

        reply = ReadToEndOfMessage(serialPort, EOL, Response, Timeout)

        return reply

    except:
        Log("Unexpected Error:")
        Log(traceback.format_exc())

def ReadToEndOfMessage(serialPort, EndChar, ExpectedReply, MaxTimeSec):
    """ Continues reading serial port till ExpectedReply and EndChar are detected or timeout is reached."""
    message = "  "
    char = ""

    timeout = time.time() + MaxTimeSec                                  # Set the timeout time

    while time.time() < timeout:                                        # Run the loop till the time out is reached or the ExpectedReply is found with an end of line.
        try:
            #Log("Chars in buffer: " + str(serialPort.inWaiting()))
            if serialPort.inWaiting() == 0:                           # Number of chars in buffer
                #Log("No Data In Buffer")
                continue

            char = serialPort.read(1)
            #Log("Char Read: " + char)
            message += char                                             # Add new character to message

            if char == EndChar:                                         # End characted been detected.
                #Log("End char detected...")
                if ExpectedReply in message:                              # Check if the expected reply is within the message so far. If yes return.
                    #Log("Expected Reply Recieved.")
                    return message

        except Exception, e:
            Log("2 Error : " +str(e))
            break

    Log("Iridium.ReadToEndOfMessage() - End Of Loop, Didn't Get Expected Reply Message: ")
    Log(message)
    Log("***********ReadToEndOfMessage() DEBUG - Checking Message been buffered:")
    ShortBurstDataStatus(serialPort)
    Log("**************************")
    time.sleep(2)
    return None

def CheckForReply(serialPort, ExpectedReply, Timeout):
    """ Read serial port till an ExpectedReply string is read or timeout. Return true if found, false if not."""
    message = "  "
    char = ""

    timeout = time.time() + Timeout                                     # Set the timeout time

    while time.time() < timeout:                                        # Run the loop till the time out is reached or the ExpectedReply is found with an end of line.
        try:

            if serialPort.inWaiting() == 0:                             # Number of chars in buffer
                #Log("No Data In Buffer")
                continue

            char = serialPort.read(1)
            #Log("Char Read: " + char)

            message += char                                             # Add new character to message

            if ExpectedReply in message:                                # Check if the expected reply is within the message so far. If yes return.
                #Log("Expected Reply Recieved.")
                return True

        except Exception, e:
            Log("Error : " +str(e))
            break

    Log("Iridium.CheckForReply() - End Of Loop, Didn't Get Expected Reply Message:")
    Log(message)
    return False


def CheckConnected(serialPort):
    """ Checks if RockBlock is connected. AT\r should receive echo."""
    Log("Iridium.CheckConnected()")

    if not WriteAndCheck(serialPort, "AT\r", "OK", 20):
        Log("Iridium Sad :(")
        return False

    Log("Iridium All Good!")
    return True

def BufferSbdMessage(serialPort, sbdMessage):
    """ This command is used to transfer a text SBD message from the DTE to the single mobile originated buffer
    in the 9602. If any data is currently in the mobile originated buffer, it will be overwritten. """

    Log("BufferSbdMessage(" + sbdMessage + ")")

    if not WriteAndCheck(serialPort, "AT+SBDWT\r", "READY", 60):                        # the 9602 will indicate to the DTE that it is prepared to receive the message by sending the string READY
        Log("Issue Buffering Message - Modem didn't reply with ready to receive.")
        return False

    Log("Modem Ready To Receive Message")
    time.sleep(3)

    if not WriteAndCheck(serialPort, sbdMessage + "\r", "0", 60):                       # Send text to buffer. The text message must be sent, terminated by a carriage return.
        Log("Problem While Buffering Message")
        return False

    time.sleep(2)
    Log("Message Buffered")

    return True

def WriteAndCheck(serialPort, WriteCommand, ExpectedReply, Timeout):
    """ Write a message to RockBlock and wait for expected reply or timeout."""
    try:
        Log("Sending Command: " + WriteCommand)

        SerialWrite(serialPort, WriteCommand)                                           # Write command to RockBlock.

        return CheckForReply(serialPort, ExpectedReply, Timeout)                        # Wait for reply or timeout.

    except:
        Log("Unexpected Error:")
        Log(traceback.format_exc())
        return False

def SerialWrite(serialPort, Message):
    """ Write message on serial port."""

    serialPort.flushInput()

    serialPort.write(Message)

    time.sleep(3)

def ShortBurstDataStatus(serialPort):
    """ This command returns current state of the mobile originated and mobile terminated buffers, and the SBD ring alert status.
    Response: +SBDSX: <MO flag>, <MOMSN>, <MT flag>, <MTMSN>, <RA flag>, <msg waiting>"""

    Log("ShortBurstDataStatus(). Checking buffers. Sending AT+SBDSX Command.")
    SerialWrite(serialPort, "AT+SBDSX\r")                                                       # Write command to 9602

    Log("Waiting for reply...")
    reply = ReadToEndOfMessage(serialPort, '\r', "+SBDSX:", 90)                                 # Read to EOL of expected response.

    if reply is not None:
        Log("Reply: ")
        Log(reply)

        reply = reply.strip()                                                                   # remove whitespace
        status = reply.split(':')[1]                                                            # Remove +SBDSX: portion of repsonse
        status = status.split(',')                                                              # Split into different codes

        MoFlag = int(status[0])                                                                 # 0 No message in mobile originated buffer. 1 Message in mobile originated buffer.
        MoMsn = int(status[1])                                                                  # The MOMSN identifies the sequence number that will be used during the next mobile originated SBD session.
        MtFlag = int(status[2])                                                                 # 0 No message in mobile terminated buffer. 1 Message in mobile terminated buffer.
        MtMsn = int(status[3])                                                                  # The MTMSN identifies the sequence number that was used in the most recent mobile terminated SBD session. This value will be -1 if there is nothing in the mobile terminated buffer.
        RaFlag = int(status[4])                                                                 # 0 No SBD ring alert. 1 SBD ring alert has been received and needs to be answered.
        MsgWaiting = int(status[5])                                                             # how many SBD Mobile Terminated messages are currently queued at the gateway awaiting collection by the ISU

        Log("MoFlag: " + str(MoFlag) + ", MtFlag: " + str(MtFlag) + ", RaFlag: " + str(RaFlag) + ", MsgWaiting: " + str(MsgWaiting))

        if MtFlag != 1 and MoFlag != 1:                                                         # Buffers are empty so no further action required.
            Log("No Message In Mobile Rx or Mobile Tx Buffer.")
            return

        if MtFlag == 1:                                                                         # Dispalys Rx message. No real use apart from debug.
            Log("Message In Mobile Rx Buffer. Reading buffer...")

            SerialWrite(serialPort, "AT+SBDRT\r")

            reply = ReadToEndOfMessage(serialPort, '\r', "OK", 60)

            Log("Rx Buffer Message:")
            Log(reply)

        if MoFlag == 1:                                                                         # Moves Tx buffer messages to Rx buffer and displays for debug.
            Log("Message in Tx Buffer. Moving to Rx buffer to read.")
            SerialWrite(serialPort, "AT+SBDTC\r")
            reply = ReadToEndOfMessage(serialPort, '\r', "SBDTC:", 60)
            Log(reply)
            SerialWrite(serialPort, "AT+SBDRT\r")
            reply = ReadToEndOfMessage(serialPort, '\r', "OK", 60)
            Log("Tx Buffer Message:")
            Log(reply)
    else:
        Log("Something wrong waiting for AT+SBDSX reply.")

def ClearBufferDebug(serialPort):
    """ This command returns current state of the mobile originated and mobile terminated buffers, and the SBD ring alert status.
    Response: +SBDSX: <MO flag>, <MOMSN>, <MT flag>, <MTMSN>, <RA flag>, <msg waiting>
    Will display any messages in buffer for debug and clear all buffers. """

    Log("Checking buffers. Sending AT+SBDSX Command.")
    SerialWrite(serialPort, "AT+SBDSX\r")                                                       # Write command to 9602

    Log("Waiting for reply...")
    reply = ReadToEndOfMessage(serialPort, '\r', "+SBDSX:", 90)                                 # Read to EOL of expected response.

    if reply is not None:
        Log("Reply: ")
        Log(reply)

        reply = reply.strip()                                                                   # remove whitespace
        status = reply.split(':')[1]                                                            # Remove +SBDSX: portion of repsonse
        status = status.split(',')                                                              # Split into different codes

        MoFlag = int(status[0])                                                                 # 0 No message in mobile originated buffer. 1 Message in mobile originated buffer.
        MoMsn = int(status[1])                                                                  # The MOMSN identifies the sequence number that will be used during the next mobile originated SBD session.
        MtFlag = int(status[2])                                                                 # 0 No message in mobile terminated buffer. 1 Message in mobile terminated buffer.
        MtMsn = int(status[3])                                                                  # The MTMSN identifies the sequence number that was used in the most recent mobile terminated SBD session. This value will be -1 if there is nothing in the mobile terminated buffer.
        RaFlag = int(status[4])                                                                 # 0 No SBD ring alert. 1 SBD ring alert has been received and needs to be answered.
        MsgWaiting = int(status[5])                                                             # how many SBD Mobile Terminated messages are currently queued at the gateway awaiting collection by the ISU

        Log("MoFlag: " + str(MoFlag) + ", MtFlag: " + str(MtFlag) + ", RaFlag: " + str(RaFlag) + ", MsgWaiting: " + str(MsgWaiting))

        if MtFlag != 1 and MoFlag != 1:                                                         # Buffers are empty so no further action required.
            Log("No Message In Mobile Rx or Mobile Tx Buffer.")
            return

        if MtFlag == 1:                                                                         # Dispalys Rx message. No real use apart from debug.
            Log("Message In Mobile Rx Buffer. Reading buffer...")

            SerialWrite(serialPort, "AT+SBDRT\r")

            reply = ReadToEndOfMessage(serialPort, '\r', "OK", 60)

            Log("Rx Buffer Message:")
            Log(reply)

        if MoFlag == 1:                                                                         # Moves Tx buffer messages to Rx buffer and displays for debug.
            Log("Message in Tx Buffer. Moving to Rx buffer to read before clearing.")
            SerialWrite(serialPort, "AT+SBDTC\r")
            reply = ReadToEndOfMessage(serialPort, '\r', "SBDTC:", 60)
            Log(reply)
            SerialWrite(serialPort, "AT+SBDRT\r")
            reply = ReadToEndOfMessage(serialPort, '\r', "OK", 60)
            Log("Tx Buffer Message:")
            Log(reply)

        Log("Clearing buffers...")                                                            # Sending a message from the 9602 to the ESS does not clear the mobile originated buffer. Reading a message from the 9602 does not clear the mobile terminated buffer.
        if not WriteAndCheck(serialPort, "AT+SBDD2\r", "0", 20):
            Log("Clearing failed.")
        Log("Buffers cleared.")
    else:
        Log("Something wrong waiting for AT+SBDSX reply.")

def ProcessMoStatus(MoStatus):
    """ Handles MoStatus options."""

    if MoStatus == 0:
        Log("MO message, if any, transferred successfully.")
        return True
    elif MoStatus == 1:
        Log("MO message, if any, transferred successfully, but the MT message in the queue was too big to be transferred.")
        return True
    elif MoStatus == 2:
        Log("MO message, if any, transferred successfully, but the requested Location Update was not accepted.")
        return True
    elif  3 <= MoStatus <= 8:
        Log("Reserved, but indicate MO session success if used.")
        return True
    elif MoStatus == 10:
        Log("Gateway reported that the call did not complete in the allowed time.")
    elif MoStatus == 11:
        Log("MO message queue at the Gateway is full.")
    elif MoStatus == 12:
        Log("MO message has too many segments.")
    elif MoStatus == 13:
        Log("Gateway reported that the session did not complete.")
    elif MoStatus == 14:
        Log("Invalid segment size.")
    elif MoStatus == 15:
        Log("Access is denied.")
    elif MoStatus == 16:
        Log("Transceiver has been locked and may not make SBD calls (see +CULK command).")
    elif MoStatus == 17:
        Log("Gateway not responding (local session timeout).")
    elif MoStatus == 18:
        Log("Connection lost (RF drop).")
    elif 19 <= MoStatus <= 31:
        Log("Reserved, but indicate MO session failure if used.")
    elif MoStatus == 32:
        Log("No network service, unable to initiate call.")
    elif MoStatus == 33:
        Log("Antenna fault, unable to initiate call.")
    elif MoStatus == 34:
        Log("Radio is disabled, unable to initiate call (see *Rn command).")
    elif MoStatus == 35:
        Log("Transceiver is busy, unable to initiate call (typically performing auto-registration).")
    elif MoStatus == 36:
        Log("Reserved, but indicate failure if used.")
    else:
        Log("Unknown code. Assume error.")

    return False

def InitiateSBD(serialPort):
    """ This command initiates an SBD session between the 9602 and the GSS. If there is a message in the mobile originated buffer it will be transferred to the GSS.
     Similarly if there is one or more MT messages queued at the GSS the oldest will be transferred to the 9602 and placed into the mobile terminated buffer. Buffers are then read and
     received messages handled appropriately. All queued messages will be read and handled.
     Response: +SBDIX:<MO status>,<MOMSN>,<MT status>,<MTMSN>,<MT length>,<MT queued>"""
    mtMsgList = []
    isMoOk = False
    isMtOk = False
    MTqueued = 0

    while isMoOk == False or isMtOk == False or MTqueued > 0:

        reply = WriteAndReceive(serialPort, "AT+SBDIX\r", "+SBDIX:", '\r', 60)                          # Send initiate command.

        if reply is not None:

            reply = reply.strip()                                                                       # remove whitespace
            reply = reply.split(':')[1]                                                                 # Remove +SBDIX: portion of repsonse
            reply = reply.split(',')                                                                    # Split into different codes

            MOstatus = int(reply[0])                                                                    # MO session status provides an indication of the disposition of the mobile originated transaction. Processed above.
            MTstatus = int(reply[2])                                                                    # 0 No MT SBD message to receive from the Gateway. 1 MT SBD message successfully received from the Gateway. 2 An error occurred while attempting to perform a mailbox check or receive a message from the Gateway.
            MTqueued = int(reply[5])                                                                    # MT queued is a count of mobile terminated SBD messages waiting at the GSS to be transferred to the 9602.

            Log("MO Status: " + str(MOstatus) + ", MT Status: " + str(MTstatus) + ", MT Queued: " + str(MTqueued))

            isMoOk = ProcessMoStatus(MOstatus)                                                          # Processes code.

            if MTstatus == 0:                                                                           # There wasn't any messages received.
                Log("No MT SBD message to receive from the Gateway.")
                isMtOk = True
            elif MTstatus == 1:                                                                         # Message was received.
                Log("MT SBD message successfully received from the Gateway.")
                mtMsg = GetText(serialPort)                                                             # Pull message from buffer.

                if mtMsg:
                    mtMsgList.append(mtMsg)                                                             # Add all messages to a list to be processed at end.

                isMtOk = True
            else:
                Log("Possible error during message retrieval. Trying again.")
                isMtOk = False                                                                          # Error receiving. Flagged to try again.

            if MTqueued > 0:                                                                            # Keep retrieving messages till all received.
                Log("More messages queued to receive.....")

            time.sleep(5)
        else:
            Log("No reply received.")
            time.sleep(3)

    return mtMsgList                                                                                    # Return the list of received messages.

def GetText(serialPort):
    """ This command is used to transfer a text SBD message from the single mobile terminated buffer in the 9602 to the DTE.
    Response: +SBDRT:<CR> {mobile terminated buffer}
    Wed Nov  5 14:56:58 2014, Received Message:   AT+SBDRT
    +SBDRT:
    05/11/14, 14:39. Test message sent while offline.
    OK
    """
    SerialWrite(serialPort, "AT+SBDRT\r")

    reply = ReadToEndOfMessage(serialPort, '\r', "OK", 60)

    if reply is None:
        Log("GetText(): Issue getting message")

    reply = reply.strip("OK\r")
    reply = reply.split('+SBDRT:\r')[1]

    return reply
