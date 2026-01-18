# Simple one-shot LoRa ping/ack test using SX1262
# Configure ROLE = 'tx' on the sender board and ROLE = 'rx' on the receiver board.
# The script initializes the radio, performs one send or one receive (with optional ACK), then exits.

import sys
try:
    import utime as time
except ImportError:
    import time

try:
    from sx1262 import SX1262
except ImportError:
    # In desktop linting environment this will fail; on-device it will work.
    SX1262 = None

import settings

ROLE = 'tx'  # 'tx' to send a ping and wait for ack, 'rx' to wait for ping and send ack
PING_TIMEOUT_MS = 10000  # RX wait time for receiver
ACK_TIMEOUT_MS = 5000    # TX wait time for ack

lora = None


def init_radio(blocking=True):
    global lora
    print('[PING] Initializing SX1262...')
    lora = SX1262(
        settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
        settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
    )
    status = lora.begin(
        freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
        syncWord=settings.SYNC_WORD, power=settings.POWER,
        currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
        implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
        tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO,
        blocking=blocking
    )
    if status != 0:
        raise RuntimeError('LoRa begin failed, status=%s' % status)
    print('[PING] Radio ready')


def send_ping_and_wait_ack():
    uid = getattr(settings, 'UNIT_ID', 'unknown')
    now = time.ticks_ms()
    msg = 'PING:%s:%d' % (uid, now)
    data = msg.encode('utf-8')
    print('[PING] TX ->', msg)
    _, st = lora.send(data)
    if st != 0:
        print('[PING] TX error:', st)
        return False
    # Switch to RX and wait for ACK
    try:
        lora.setOperatingMode(lora.MODE_RX)
    except Exception:
        pass
    print('[PING] Waiting for ACK...')
    pkt, err = lora.recv(0, True, ACK_TIMEOUT_MS)
    if err == 0 and pkt:
        try:
            s = pkt.decode('utf-8', 'ignore')
        except Exception:
            s = str(pkt)
        print('[PING] RX <-', s)
        if s.startswith('ACK:'):
            print('[PING] ACK received')
            return True
        else:
            print('[PING] Non-ACK response')
            return False
    else:
        print('[PING] ACK timeout or error:', err)
        return False


def wait_ping_and_send_ack():
    print('[PING] RX waiting for PING for up to %d ms...' % PING_TIMEOUT_MS)
    pkt, err = lora.recv(0, True, PING_TIMEOUT_MS)
    if err == 0 and pkt:
        try:
            s = pkt.decode('utf-8', 'ignore')
        except Exception:
            s = str(pkt)
        print('[PING] RX <-', s)
        if s.startswith('PING:'):
            # Build ACK
            parts = s.split(':', 2)
            uid = parts[1] if len(parts) > 1 else 'unknown'
            ack = ('ACK:%s:%d' % (uid, time.ticks_ms())).encode('utf-8')
            print('[PING] TX ->', ack)
            _, st = lora.send(ack)
            if st != 0:
                print('[PING] ACK TX error:', st)
                return False
            print('[PING] ACK sent')
            return True
        else:
            print('[PING] Unexpected message, no ACK sent')
            return False
    else:
        print('[PING] RX timeout or error:', err)
        return False


def deinit_radio():
    global lora
    if lora is None:
        return
    print('[PING] Deinitializing radio...')
    try:
        lora.standby()
    except Exception:
        pass
    try:
        if hasattr(lora, 'spi') and lora.spi:
            lora.spi.deinit()
    except Exception:
        pass
    lora = None


def main():
    try:
        init_radio(blocking=True)
        ok = False
        if ROLE == 'tx':
            ok = send_ping_and_wait_ack()
        else:
            ok = wait_ping_and_send_ack()
        print('[PING] Result:', 'SUCCESS' if ok else 'FAIL')
    except Exception as e:
        print('[PING] Exception:', e)
    finally:
        deinit_radio()


if __name__ == '__main__':
    main()
