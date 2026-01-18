import asyncio, time, os, json
import settings
if not getattr(settings, 'LORA_SIMULATE', False):
    print('Skipping lora_selective_retransmit (LORA_SIMULATE disabled)')
    raise SystemExit(0)
import lora

async def run_test_drop_chunk_ack():
    # test config quick timeouts
    settings.LORA_SIMULATE = True
    settings.LORA_PER_CHUNK_RETRIES = 3
    settings.LORA_PER_CHUNK_ACK_TIMEOUT_MS = 200
    settings.LORA_ACK_TIMEOUT_MS = 500

    base = lora.create_sim_radio('base')
    remote = lora.create_sim_radio('remote')

    # We'll drop the first chunk_ack for chunk_idx=1 of the message to force retransmit
    drop_for_mid = {'mid': None, 'dropped': False, 'target_idx': 1}

    # Custom base receiver that sends chunk_ack for every chunk except the first time we see target_idx==1 for a given mid
    async def base_receiver():
        seen_chunks = {}
        while True:
            pkt, st = base.recv(0, True, 2000)
            if st == 0 and pkt:
                try:
                    j = json.loads(pkt.decode('utf-8'))
                except Exception:
                    j = None
                if not isinstance(j, dict):
                    await asyncio.sleep(0.01); continue
                t = j.get('type')
                if t == 'telemetry':
                    mid = j.get('mid'); idx = int(j.get('chunk_idx', 0))
                    key = f"{mid}:{idx}"
                    seen_chunks[key] = seen_chunks.get(key, 0) + 1
                    # If this is the configured target chunk and not yet dropped, skip sending chunk_ack once
                    if idx == drop_for_mid['target_idx'] and not drop_for_mid['dropped']:
                        drop_for_mid['mid'] = mid
                        drop_for_mid['dropped'] = True
                        # intentionally drop (no ack)
                    else:
                        # send chunk_ack
                        ack = {'schema': 'tmon/v1', 'type': 'chunk_ack', 'unit_id': j.get('unit_id'), 'mid': mid, 'chunk_idx': idx, 'result': 'ok'}
                        base.send(json.dumps(ack).encode('utf-8'))
                    # attempt assemble -> persist & final ack if complete
                    lora._save_chunk(j.get('mid'), j.get('chunk_idx'), j.get('chunks'), j.get('data','').encode('utf-8'), meta_unit=j.get('unit_id'))
                    assembled = lora._try_assemble(j.get('mid'))
                    if assembled:
                        try:
                            payload = json.loads(assembled.decode('utf-8'))
                        except Exception:
                            payload = None
                        if isinstance(payload, dict):
                            # persist to field_data.log and send final ack
                            try:
                                open(settings.FIELD_DATA_LOG, 'a').write(json.dumps(payload) + '\n')
                            except Exception:
                                pass
                            base.send(json.dumps({'schema':'tmon/v1', 'type':'ack', 'unit_id': payload.get('unit_id'), 'mid': j.get('mid'), 'result':'ok'}).encode('utf-8'))
                elif t == 'chunk_ack':
                    pass
                elif t == 'ack':
                    pass
            await asyncio.sleep(0.01)

    # Start base receiver
    asyncio.create_task(base_receiver())
    # Set remote as active lora instance for send_field_data
    lora.lora = remote

    payload = {'unit_id': 'SIM-TEST', 'data': 'x'*900}  # forces multiple chunks
    ok = await lora.send_field_data(payload, retries=4)
    print('test send returned:', ok)
    assert ok is True

    # Give base time to persist
    await asyncio.sleep(0.5)
    # Verify persisted last line matches unit
    try:
        with open(settings.FIELD_DATA_LOG, 'r') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            last = json.loads(lines[-1]) if lines else None
    except Exception:
        last = None
    assert isinstance(last, dict) and last.get('unit_id') == 'SIM-TEST'
    print('Selective retransmit test passed')

if __name__ == '__main__':
    try:
        asyncio.run(run_test_drop_chunk_ack())
    except Exception as e:
        print('Test failed:', e)
