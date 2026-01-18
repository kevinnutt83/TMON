import asyncio, os, ujson as json, time
import settings
import lora

# Quick sim runner to validate chunk/ack/reassembly
async def run_test():
    settings.LORA_SIMULATE = True
    # create two sim radios
    base = lora.create_sim_radio('base')
    remote = lora.create_sim_radio('remote')
    # start base receiver loop for base radio (independent of global lora.lora)
    # Start base receiver for the base radio (handles chunk ack + final ack)
    asyncio.create_task(lora._receiver_loop_for_radio(base))
    # use remote radio as the 'current' radio for send_field_data (it reads lora.lora global)
    lora.lora = remote
    payload = {'unit_id': 'SIM-001', 'a': 1, 'data': 'x'*1000}  # large payload forces chunking
    ok = await lora.send_field_data(payload, retries=3)
    print('Send returned', ok)
    # give base time to assemble and reply
    await asyncio.sleep(1)
    # validate that the file was appended to FIELD_DATA_LOG
    try:
        with open(settings.FIELD_DATA_LOG, 'r') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            last = json.loads(lines[-1]) if lines else None
    except Exception:
        last = None
    print('Last persisted payload unit_id:', last.get('unit_id') if isinstance(last, dict) else None)
    assert ok is True
    assert isinstance(last, dict) and last.get('unit_id') == 'SIM-001'
    print('Lora sim test passed')

if __name__ == '__main__':
    # Quick runner for desktop mode
    try:
        asyncio.run(run_test())
    except Exception as e:
        print('Test runner error:', e)

# New additional test file to simulate ACK loss and force retry
# filepath: c:\Users\kevin\OneDrive\TMON Development\DevOps\TMON\TMON-main\micropython\tests\lora_sim_retry.py
import asyncio, time, json
import settings
import lora

async def run_retry_test():
    settings.LORA_SIMULATE = True
    base = lora.create_sim_radio('base')
    remote = lora.create_sim_radio('remote')
    # monkeypatch base receiver to drop first final ack for specified mid to force retry:
    dropped = {'mid': None, 'dropped_once': False}
    async def base_receiver_with_drop():
        while True:
            pkt, st = base.recv(0, True, 3000)
            if st == 0 and pkt:
                try:
                    j = json.loads(pkt.decode('utf-8'))
                except Exception:
                    j = None
                if isinstance(j, dict) and j.get('type') == 'telemetry':
                    # normal storage behavior
                    lora._save_chunk(j.get('mid'), j.get('chunk_idx'), j.get('chunks'), j.get('data', '').encode('utf-8'), meta_unit=j.get('unit_id'))
                    assembled = lora._try_assemble(j.get('mid'))
                    if assembled:
                        # On first attempt, drop final ack to force a retry, then send ack next time
                        mid = j.get('mid')
                        if not dropped['dropped_once']:
                            dropped['mid'] = mid
                            dropped['dropped_once'] = True
                            # do not send ack first time (simulate loss)
                        else:
                            # send ack
                            base.send(json.dumps({'schema':'tmon/v1','type':'ack','unit_id':j.get('unit_id'),'mid':mid,'result':'ok'}).encode('utf-8'))
                elif isinstance(j, dict) and j.get('type') == 'chunk_ack':
                    # noop for this test
                    pass
            await asyncio.sleep(0.01)
    asyncio.create_task(base_receiver_with_drop())
    lora.lora = remote
    payload = {'unit_id': 'SIM-002', 'x': 1, 'data': 'x' * 1500}
    ok = await lora.send_field_data(payload, retries=4)
    print('retry send returned', ok)
    assert ok is True
    print('Retry test passed')

if __name__ == '__main__':
    try:
        asyncio.run(run_retry_test())
    except Exception as e:
        print('Retry test error:', e)
