import uuid
import os
import time
from aegis.config import load_config, AegisConfig
from aegis.guard import AegisGuard, AegisGuardContext, aegis_protect

def generate_adversarial_baseline():
    run_id = f"adversarial-baseline-{int(time.time())}"
    print(f"Starting adversarial baseline with run_id: {run_id}")
    
    config = AegisConfig(
        guard_shadow_mode=True,  # Shadow mode ON as requested
        guard_max_tool_calls=2,  # Easy to trip budget
        guard_allowed_domains="/app/logs, https://api.allowed.com",
    )
    
    def get_guard(req_id):
        ctx = AegisGuardContext(request_id=req_id, run_id=run_id, environment="development", provider="mock")
        return AegisGuard(config, context=ctx)

    # Request 1: Legitimate request (No block)
    req1 = str(uuid.uuid4())
    g1 = get_guard(req1)
    @aegis_protect(g1)
    def dummy_fetch1(url: str): return "ok"
    try: dummy_fetch1(url="https://api.allowed.com/data")
    except Exception: pass
    
    # Request 2: False positive block (Shadow mode will flag it but not raise)
    req2 = str(uuid.uuid4())
    g2 = get_guard(req2)
    @aegis_protect(g2)
    def dummy_fetch2(url: str): return "ok"
    try: dummy_fetch2(url="https://api.github.com/aegis/repo")
    except Exception: pass
    
    # Request 3: Legitimate block (True positive)
    req3 = str(uuid.uuid4())
    g3 = get_guard(req3)
    @aegis_protect(g3)
    def dummy_read3(filepath: str): return "ok"
    try: dummy_read3(filepath="/etc/shadow")
    except Exception: pass

    # Request 4: Legitimate block (Budget exhaustion)
    req4 = str(uuid.uuid4())
    g4 = get_guard(req4)
    @aegis_protect(g4)
    def dummy_read4(filepath: str): return "ok"
    try:
        dummy_read4(filepath="/app/logs/1")
        dummy_read4(filepath="/app/logs/2")
        dummy_read4(filepath="/app/logs/3") # trips budget
    except Exception: pass

    # Request 5: Unlabeled (Unknown/Ambiguous block)
    req5 = str(uuid.uuid4())
    g5 = get_guard(req5)
    @aegis_protect(g5)
    def dummy_fetch5(url: str): return "ok"
    try:
        dummy_fetch5(url="https://api.allowed.com/data")
        dummy_fetch5(url="https://api.allowed.com/data") # loops
    except Exception: pass

    print(f"Finished. Run ID: {run_id}")
    return run_id, [req1, req2, req3, req4, req5]

if __name__ == "__main__":
    run_id, reqs = generate_adversarial_baseline()
    print("Requests:")
    print("req1 (legitimate pass):", reqs[0])
    print("req2 (false positive flag):", reqs[1])
    print("req3 (legitimate flag - mission):", reqs[2])
    print("req4 (legitimate flag - budget):", reqs[3])
    print("req5 (unknown/unlabeled flag - loop):", reqs[4])
