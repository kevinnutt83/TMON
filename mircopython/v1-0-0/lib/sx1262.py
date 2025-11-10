# Updated sx1262.py

from _sx126x import *
from sx126x import SX126X

_SX126X_PA_CONFIG_SX1262 = const(0x00)

# Define necessary constants
ERR_NONE = 0
ERR_INVALID_FREQUENCY = -1
ERR_INVALID_OUTPUT_POWER = -2
ERR_UNKNOWN = -99
ERR_PACKET_TOO_LONG = -3
ERR_RX_TIMEOUT = -4
ERR_CRC_MISMATCH = -5
ERR_TX_TIMEOUT = -6
ERR_INVALID_PACKET_TYPE = -7
ERR_WRONG_MODEM = -8

class SX1262(SX126X):
    TX_DONE = SX126X_IRQ_TX_DONE
    RX_DONE = SX126X_IRQ_RX_DONE
    ADDR_FILT_OFF = SX126X_GFSK_ADDRESS_FILT_OFF
    ADDR_FILT_NODE = SX126X_GFSK_ADDRESS_FILT_NODE
    ADDR_FILT_NODE_BROAD = SX126X_GFSK_ADDRESS_FILT_NODE_BROADCAST
    PREAMBLE_DETECT_OFF = SX126X_GFSK_PREAMBLE_DETECT_OFF
    PREAMBLE_DETECT_8 = SX126X_GFSK_PREAMBLE_DETECT_8
    PREAMBLE_DETECT_16 = SX126X_GFSK_PREAMBLE_DETECT_16
    PREAMBLE_DETECT_24 = SX126X_GFSK_PREAMBLE_DETECT_24
    PREAMBLE_DETECT_32 = SX126X_GFSK_PREAMBLE_DETECT_32

    MODE_TX = "TX"
    MODE_RX = "RX"
    MODE_STDBY = "STDBY"

    def __init__(self, spi_bus, clk, mosi, miso, cs, irq, rst, gpio):
        super().__init__(spi_bus, clk, mosi, miso, cs, irq, rst, gpio)
        self._callbackFunction = self._dummyFunction

    def begin(self, freq=434.0, bw=125.0, sf=9, cr=7, syncWord=SX126X_SYNC_WORD_PRIVATE,
              power=14, currentLimit=60.0, preambleLength=8, implicit=False, implicitLen=0xFF,
              crcOn=True, txIq=False, rxIq=False, tcxoVoltage=1.6, useRegulatorLDO=False,
              blocking=True):
        state = super().begin(bw, sf, cr, syncWord, currentLimit, preambleLength, tcxoVoltage, useRegulatorLDO, txIq, rxIq)
        if state != ERR_NONE:
            return state

        if not implicit:
            state = super().explicitHeader()
        else:
            state = super().implicitHeader(implicitLen)
        if state != ERR_NONE:
            return state

        state = super().setCRC(crcOn)
        if state != ERR_NONE:
            return state

        state = self.setFrequency(freq)
        if state != ERR_NONE:
            return state

        state = self.setOutputPower(power)
        if state != ERR_NONE:
            return state

        state = super().fixPaClamping()
        if state != ERR_NONE:
            return state

        state = self.setBlockingCallback(blocking)

        return state

    def beginFSK(self, freq=434.0, br=48.0, freqDev=50.0, rxBw=156.2, power=14, currentLimit=60.0,
                 preambleLength=16, dataShaping=0.5, syncWord=[0x2D, 0x01], syncBitsLength=16,
                 addrFilter=SX126X_GFSK_ADDRESS_FILT_OFF, addr=0x00, crcLength=2, crcInitial=0x1D0F, crcPolynomial=0x1021,
                 crcInverted=True, whiteningOn=True, whiteningInitial=0x0100,
                 fixedPacketLength=False, packetLength=0xFF, preambleDetectorLength=SX126X_GFSK_PREAMBLE_DETECT_16,
                 tcxoVoltage=1.6, useRegulatorLDO=False,
                 blocking=True):
        state = super().beginFSK(br, freqDev, rxBw, currentLimit, preambleLength, dataShaping, preambleDetectorLength, tcxoVoltage, useRegulatorLDO)
        if state != ERR_NONE:
            return state

        state = super().setSyncBits(syncWord, syncBitsLength)
        if state != ERR_NONE:
            return state

        if addrFilter == SX126X_GFSK_ADDRESS_FILT_OFF:
            state = super().disableAddressFiltering()
        elif addrFilter == SX126X_GFSK_ADDRESS_FILT_NODE:
            state = super().setNodeAddress(addr)
        elif addrFilter == SX126X_GFSK_ADDRESS_FILT_NODE_BROADCAST:
            state = super().setBroadcastAddress(addr)
        else:
            state = ERR_UNKNOWN
        if state != ERR_NONE:
            return state

        state = super().setCRC(crcLength, crcInitial, crcPolynomial, crcInverted)
        if state != ERR_NONE:
            return state

        state = super().setWhitening(whiteningOn, whiteningInitial)
        if state != ERR_NONE:
            return state

        if fixedPacketLength:
            state = super().fixedPacketLengthMode(packetLength)
        else:
            state = super().variablePacketLengthMode(packetLength)
        if state != ERR_NONE:
            return state

        state = self.setFrequency(freq)
        if state != ERR_NONE:
            return state

        state = self.setOutputPower(power)
        if state != ERR_NONE:
            return state

        state = super().fixPaClamping()
        if state != ERR_NONE:
            return state

        state = self.setBlockingCallback(blocking)

        return state

    def setFrequency(self, freq, calibrate=True):
        if freq < 150.0 or freq > 960.0:
            return ERR_INVALID_FREQUENCY

        state = ERR_NONE

        if calibrate:
            data = bytearray(2)
            if freq > 900.0:
                data[0] = SX126X_CAL_IMG_902_MHZ_1
                data[1] = SX126X_CAL_IMG_902_MHZ_2
            elif freq > 850.0:
                data[0] = SX126X_CAL_IMG_863_MHZ_1
                data[1] = SX126X_CAL_IMG_863_MHZ_2
            elif freq > 770.0:
                data[0] = SX126X_CAL_IMG_779_MHZ_1
                data[1] = SX126X_CAL_IMG_779_MHZ_2
            elif freq > 460.0:
                data[0] = SX126X_CAL_IMG_470_MHZ_1
                data[1] = SX126X_CAL_IMG_470_MHZ_2
            else:
                data[0] = SX126X_CAL_IMG_430_MHZ_1
                data[1] = SX126X_CAL_IMG_430_MHZ_2
            state = super().calibrateImage(data)
            if state != ERR_NONE:
                return state

        return super().setFrequencyRaw(freq)

    def setOutputPower(self, power):
        if not ((power >= -9) and (power <= 22)):
            return ERR_INVALID_OUTPUT_POWER

        ocp = bytearray(1)
        ocp_mv = memoryview(ocp)
        state = super().readRegister(SX126X_REG_OCP_CONFIGURATION, ocp_mv, 1)
        if state != ERR_NONE:
            return state

        state = super().setPaConfig(0x04, _SX126X_PA_CONFIG_SX1262)
        if state != ERR_NONE:
            return state

        state = super().setTxParams(power)
        if state != ERR_NONE:
            return state

        return super().writeRegister(SX126X_REG_OCP_CONFIGURATION, ocp, 1)

    def setTxIq(self, txIq):
        self._txIq = txIq

    def setRxIq(self, rxIq):
        self._rxIq = rxIq
        if not self.blocking:
            state = super().startReceive()
            if state != ERR_NONE:
                return state

    def setPreambleDetectorLength(self, preambleDetectorLength):
        self._preambleDetectorLength = preambleDetectorLength
        if not self.blocking:
            state = super().startReceive()
            if state != ERR_NONE:
                return state

    def setBlockingCallback(self, blocking, callback=None):
        self.blocking = blocking
        if not self.blocking:
            state = super().startReceive()
            if state != ERR_NONE:
                return state
            if callback is not None:
                self._callbackFunction = callback
                super().setDio1Action(self._onIRQ)
            else:
                self._callbackFunction = self._dummyFunction
                super().clearDio1Action()
            return state
        else:
            state = super().standby()
            if state != ERR_NONE:
                return state
            self._callbackFunction = self._dummyFunction
            super().clearDio1Action()
            return state

    def setOperatingMode(self, mode):
        """Set the operating mode of the SX1262 module."""
        if mode == self.MODE_TX:
            return self.setTx()
        elif mode == self.MODE_RX:
            return self.setRx(SX126X_RX_TIMEOUT_INF)
        elif mode == self.MODE_STDBY:
            return self.standby()
        else:
            return ERR_UNKNOWN

    def recv(self, len=0, timeout_en=False, timeout_ms=0):
        if not self.blocking:
            return self._readData(len)
        else:
            return self._receive(len, timeout_en, timeout_ms)

    def send(self, data):
        if not self.blocking:
            return self._startTransmit(data)
        else:
            return self._transmit(data)

    def _events(self):
        return super().getIrqStatus()

    def _receive(self, len_=0, timeout_en=False, timeout_ms=0):
        state = ERR_NONE
        
        length = len_
        
        if len_ == 0:
            length = SX126X_MAX_PACKET_LENGTH

        data = bytearray(length)
        data_mv = memoryview(data)

        state = super().receive(data_mv, length, timeout_en, timeout_ms)

        if state == ERR_NONE or state == ERR_CRC_MISMATCH:
            if len_ == 0:
                length = super().getPacketLength(False)
                data = data[:length]

        else:
            return b'', state

        return  bytes(data), state

    def _transmit(self, data):
        if isinstance(data, bytes) or isinstance(data, bytearray):
            pass
        else:
            return 0, ERR_INVALID_PACKET_TYPE

        state = super().transmit(data, len(data))
        return len(data), state

    def _readData(self, len_=0):
        state = ERR_NONE

        length = super().getPacketLength()

        if len_ < length and len_ != 0:
            length = len_

        data = bytearray(length)
        data_mv = memoryview(data)

        state = super().readData(data_mv, length)

        state2 = super().startReceive()
        if state2 != ERR_NONE:
            return b'', state2

        if state == ERR_NONE or state == ERR_CRC_MISMATCH:
            return bytes(data), state

        else:
            return b'', state

    def _startTransmit(self, data):
        if isinstance(data, bytes) or isinstance(data, bytearray):
            pass
        else:
            return 0, ERR_INVALID_PACKET_TYPE

        state = super().startTransmit(data, len(data))
        return len(data), state

    def _dummyFunction(self, *args):
        pass

    def _onIRQ(self, callback):
        events = self._events()
        if events & SX126X_IRQ_TX_DONE:
            super().startReceive()
        self._callbackFunction(events)