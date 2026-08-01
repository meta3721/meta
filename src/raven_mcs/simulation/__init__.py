"""Simulation / EventTrace generators."""

from raven_mcs.simulation.event_trace import (
    EventTrace,
    freeze_event_trace,
    synthesize_event_trace,
    verify_event_trace_hash,
)
from raven_mcs.simulation.observation_generator import (
    ObservationConfig,
    generate_observations_for_trace,
)
from raven_mcs.simulation.opportunity_generator import (
    OpportunityConfig,
    generate_opportunity_stream,
)
from raven_mcs.simulation.replay import check_mc_accuracy, mc_replay_q
from raven_mcs.simulation.usable_generator import (
    UsableConfig,
    generate_q_oracle,
    generate_usable_events,
)

__all__ = [
    "EventTrace",
    "freeze_event_trace",
    "synthesize_event_trace",
    "verify_event_trace_hash",
    "OpportunityConfig",
    "generate_opportunity_stream",
    "ObservationConfig",
    "generate_observations_for_trace",
    "UsableConfig",
    "generate_usable_events",
    "generate_q_oracle",
    "mc_replay_q",
    "check_mc_accuracy",
]
