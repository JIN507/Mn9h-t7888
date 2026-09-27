"""Origin v2 orchestrator — Phase 0 skeleton. Phases 1-3 fill this in
(see ORIGIN_V2_PLAN.md §5-6). Until then it reports itself as unavailable
so the job runner falls back to v1."""
from origin.budget import Budget


def investigate(image_url, *, progress=None, extra_frame_urls=None):
    budget = Budget(kind='video' if extra_frame_urls else 'image')
    return {'success': False, 'engine': 'origin_v2', 'note': 'Origin v2 not built yet (phase 0)',
            'first_seen': None, 'timeline': [], 'engines': {}, 'budget': budget.snapshot()}
