import time
from uuid import uuid4
from worldsim.application.context.assembler import assemble
from worldsim.application.orchestration.stage1 import DECISION_SECTION_BUDGETS
from worldsim.domain.context import ContextRequest, SourceCandidate
from worldsim.domain.enums import Visibility
from worldsim.domain.memory import score_salience

me = uuid4()
def run(rows: int, facts: int = 3) -> float:
    t0 = time.perf_counter()
    cands = []
    for r in range(rows):
        age = r
        for f in range(facts):
            cands.append(SourceCandidate(source_id=f"obs:{uuid4()}:k{f}", data_class="observations",
                visibility=Visibility.PRIVATE, owner_id=me,
                text=f"Day {r//10}, phase {r%10}: someone said something rather ordinary about the market {f}",
                score=score_salience(3.0, age, 40), created_phase_index=max(0, 10000-age)))
    req = ContextRequest(role="character_decision", actor_id=me, world_id=uuid4(), phase_run_id=uuid4(),
        snapshot_id=uuid4(), purpose="decide next intent", section_budgets=DECISION_SECTION_BUDGETS)
    assemble(req, cands)
    return (time.perf_counter() - t0) * 1000
run(50)
for rows in (40, 120, 239, 400, 1000, 3000):
    print(rows, "rows:", round(min(run(rows) for _ in range(5)), 1), "ms")
