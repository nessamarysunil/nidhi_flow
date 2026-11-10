import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import init_db, get_members, clear_members, load_sample_members, add_member, DB_PATH
from core.gnani_client import parse_voice_onboarding, extract_onboarding_from_text

def test_voice_onboarding_extraction():
    print("Testing Voice Onboarding Group & Member extraction rules...")

    # Case 1: Group Name + Officers + Members
    t1 = "Suryakanthi Koottayma, Leela Secretary, Radha President, Chitra, Meera"
    res1 = extract_onboarding_from_text(t1)
    assert res1["group_name"] == "Suryakanthi Koottayma", f"Expected 'Suryakanthi Koottayma', got '{res1['group_name']}'"
    assert len(res1["members"]) == 4, f"Expected 4 members, got {len(res1['members'])}"
    assert res1["members"][0] == {"name": "Leela", "role": "secretary"}
    assert res1["members"][1] == {"name": "Radha", "role": "president"}
    assert res1["members"][2] == {"name": "Chitra", "role": "member"}
    assert res1["members"][3] == {"name": "Meera", "role": "member"}
    print("✓ Case 1 Passed: 'Suryakanthi Koottayma' + Leela (sec), Radha (pres), Chitra, Meera")

    # Case 2: Haritha Sangham + Members
    t2 = "Haritha Sangham, Shobhana, Anitha"
    res2 = extract_onboarding_from_text(t2)
    assert res2["group_name"] == "Haritha Sangham", f"Expected 'Haritha Sangham', got '{res2['group_name']}'"
    assert len(res2["members"]) == 2
    assert res2["members"][0]["name"] == "Shobhana"
    assert res2["members"][1]["name"] == "Anitha"
    print("✓ Case 2 Passed: 'Haritha Sangham' + Shobhana, Anitha")

    # Case 3: Malayalam script input
    t3 = "സൂര്യകാന്തി കൂട്ടായ്മ, ലീല സെക്രട്ടറി, രാധ പ്രസിഡന്റ്, ചിത്ര"
    res3 = extract_onboarding_from_text(t3)
    assert "കൂട്ടായ്മ" in res3["group_name"]
    assert len(res3["members"]) == 3
    assert res3["members"][0]["name"] == "Leela" and res3["members"][0]["role"] == "secretary"
    assert res3["members"][1]["name"] == "Radha" and res3["members"][1]["role"] == "president"
    print("✓ Case 3 Passed: Malayalam script group and members correctly extracted and mapped")

    # Case 4: Group Name only (e.g. Ward 4 Kudumbashree)
    t4 = "Ward 4 Kudumbashree"
    res4 = extract_onboarding_from_text(t4)
    assert res4["group_name"] == "Ward 4 Kudumbashree"
    assert len(res4["members"]) == 0
    print("✓ Case 4 Passed: Group Name only correctly extracted without false members")

    # Case 5: Members only (no group name spoken)
    t5 = "Leela Secretary, Radha President, Chitra"
    res5 = extract_onboarding_from_text(t5)
    assert res5["group_name"] is None
    assert len(res5["members"]) == 3
    print("✓ Case 5 Passed: Members only correctly extracted with group_name=None")

def test_db_onboarding_helpers():
    print("Testing DB onboarding helpers (clear_members, add_member, load_sample_members)...")
    test_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_onboarding.db")
    if os.path.exists(test_db):
        os.remove(test_db)

    init_db(test_db)
    mems = get_members(test_db)
    assert len(mems) == 5, f"Expected 5 seeded members, got {len(mems)}"
    print(f"✓ Initial seeded members: {[m['name'] for m in mems]}")

    # Test clear_members
    clear_members(test_db)
    mems_empty = get_members(test_db)
    assert len(mems_empty) == 0, f"Expected 0 members after clear, got {len(mems_empty)}"
    print("✓ clear_members successfully emptied the roster")

    # Test add_member
    add_member("Shobhana", "secretary", test_db)
    add_member("Anitha", "president", test_db)
    add_member("Bindu", "member", test_db)
    mems_new = get_members(test_db)
    assert len(mems_new) == 3
    assert mems_new[0]["name"] == "Shobhana" and mems_new[0]["role"] == "secretary"
    assert mems_new[1]["name"] == "Anitha" and mems_new[1]["role"] == "president"
    assert mems_new[2]["name"] == "Bindu" and mems_new[2]["role"] == "member"
    print(f"✓ add_member added custom roster: {[m['name'] for m in mems_new]}")

    # Test load_sample_members
    load_sample_members(test_db)
    mems_loaded = get_members(test_db)
    names = [m["name"] for m in mems_loaded]
    assert "Leela" in names and "Radha" in names and "Chitra" in names
    print(f"✓ load_sample_members restored standard roster: {names}")

    if os.path.exists(test_db):
        os.remove(test_db)
    print("All DB onboarding helper tests PASSED!")

if __name__ == "__main__":
    test_voice_onboarding_extraction()
    test_db_onboarding_helpers()

