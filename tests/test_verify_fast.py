import sys, threading
sys.path.insert(0, 'sim')
from crypto_gate import ZKTAT, HPO, RevocationBloomFilter
from trust_supervisor import CyberAdaptTrustController
from sim_integrated import run, run_live, CFG, N

results = []
def t(name, ok):
    results.append((name, ok))
    print(('PASS' if ok else 'FAIL') + '  ' + name)

print('--- Crypto ---')
tok = ZKTAT.prove(1, 'ctx')
t('zktat_roundtrip', all(ZKTAT.verify(ZKTAT.prove(v,'c'),'c') for v in range(1,8)))
t('zktat_wrong_ctx', not ZKTAT.verify(tok,'wrong'))
f2 = dict(tok); f2['s2'] = (tok['s2']+1) % (2**256)
t('zktat_forgery', not ZKTAT.verify(f2,'ctx'))
tag = HPO.compute_tag('ATTR', b'sec')
t('hpo_roundtrip', HPO.match_policy(tag,'ATTR',b'sec'))
t('hpo_wrong_key', not HPO.match_policy(tag,'ATTR',b'bad'))
t('hpo_wrong_attr', not HPO.match_policy(tag,'OTHER',b'sec'))
b = RevocationBloomFilter(); b.add('v1')
t('bloom', b.is_revoked('v1') and not b.is_revoked('v2'))
ctrl = CyberAdaptTrustController()
ws = []
for s in range(11):
    r = ctrl.process_telemetry_step('1',0.0,14.0,14.0,0.0,14.0,float(s),0.1)
    ws.append(r.get('trust_weight_w', r.get('w',1.0)))
t('trust_bounds', all(0.05<=w<=1.0 for w in ws))

print('--- CFG ---')
t('cfg_ma_key', 'D1_ma_abse_ar' in CFG)
t('cfg_ma_fields', CFG['D1_ma_abse_ar'].get('gate') and CFG['D1_ma_abse_ar'].get('crypto') and CFG['D1_ma_abse_ar'].get('trust') is None)
t('cfg_8_keys', set(CFG.keys())=={'D0_none','D1_crypto','D1_ma_abse_ar','D2_binary_hnom','D2b_binary_hfail','CA_full','CA_norevoke','CA_fixedh'})

print('--- run_live ---')
stop=threading.Event(); inj=threading.Event()
gen=run_live('D1_ma_abse_ar','L1_normal',1,inj,stop)
states=[]
for i,s in enumerate(gen):
    states.append(s)
    if i>=9: stop.set(); break
t('states_10', len(states)==10)
t('state_keys', all(k in states[0] for k in ['t','x','v','w','S','gap','h','last_crypto','cfg','attack_active']))
t('x_len_8', len(states[0]['x'])==N)
t('gap_len_7', len(states[0]['gap'])==N-1)
stop2=threading.Event(); inj2=threading.Event(); stop2.set()
t('stop_flag', list(run_live('D0_none','L1_normal',1,inj2,stop2))==[])
stop3=threading.Event(); inj3=threading.Event(); inj3.set()
found=False
for i,s in enumerate(run_live('CA_full','L1_normal',1,inj3,stop3)):
    if i>5 and s['attack_active']: found=True; stop3.set(); break
t('inject_flag', found)

print('--- D0_none batch (fast) ---')
r0 = run('D0_none','L1_normal',1)
t('d0_schema', all(k in r0 for k in ['min_gap','collision','crypto']))
t('d0_no_crypto', r0['crypto']['mean_zktat_prove_us']==0.0 and r0['crypto']['zktat_pass_rate']==0.0)
t('d0_safe', not r0['collision'] and r0['min_gap']>0)

print('--- SSE frame ---')
stop4=threading.Event(); inj4=threading.Event()
frame=next(run_live('D1_ma_abse_ar','L1_normal',1,inj4,stop4)); stop4.set()
t('frame_x8', len(frame['x'])==8)
t('frame_gap7', len(frame['gap'])==7)
t('frame_w_range', all(0.0<=w<=1.0 for w in frame['w']))
t('frame_S_range', all(0.0<=s<=1.0 for s in frame['S']))
t('frame_attack_bool', isinstance(frame['attack_active'],bool))

passed=sum(1 for _,p in results if p)
print('')
print('TOTAL: '+str(passed)+'/'+str(len(results))+' passed')
if passed==len(results): print('ALL FAST TESTS PASSED')
else:
    for n,p in results:
        if not p: print('FAILED: '+n)
