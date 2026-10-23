"""Shim: the /leetcode Stop gate lives in ~/src/leetcode-guard (leetcode_coach.stop_gate)."""
import os
if __name__ == "__main__": os.execv("/usr/bin/python3", ["/usr/bin/python3", "-P", "-m", "leetcode_coach.stop_gate"])
