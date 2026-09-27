# Behavior trees

**VERIFIED:** [BehaviorTree.CPP](https://github.com/BehaviorTree/BehaviorTree.CPP) provides sequences, selectors, decorators, asynchronous actions, XML tree descriptions, blackboards, subtree reuse and transition logging. Its [reactive sequence implementation](https://github.com/BehaviorTree/BehaviorTree.CPP/blob/master/src/controls/reactive_sequence.cpp) reevaluates earlier children and halts a previously running child when priority changes. These are concrete semantics to define if MegaMod adopts trees; the library's C++17 code is not itself a design requirement for MegaMod's C engine.

| Node | Semantics to specify |
|---|---|
| sequence | run children until one fails or runs; retain or restart child index explicitly |
| selector | choose first successful/running child; order becomes priority |
| decorator | invert, timeout, repeat, cooldown or guard, each with bounded behavior |
| leaf action | return running/success/failure; support cancellation and failure code |

**Abort semantics are the hard part.** A guard changing from true to false while `move_to` runs must cancel or retarget the move, release any reservation and report a reason. Event-driven wakeups reduce repeated full-tree ticks, but events cannot replace periodic reevaluation where world state changes without an event. Subtree parameters and typed blackboard keys need load-time validation; serialization should describe nodes and references, not raw pointers or closures. A debug viewer should highlight the active path, last transition and guard value.

**Recommendation:** do not make BTs the first AI milestone. A small explicit patrol/investigate/chase decision is enough to validate navigation, perception, action completion and replication. Add BT resources only when repeated branching behaviors need authoring reuse and debug tooling exists. If tried later, compare a compact engine-native runtime with permissive libraries; [BehaviorTree.CPP's MIT license](https://github.com/BehaviorTree/BehaviorTree.CPP/blob/master/LICENSE) permits use with notice, but integration cost and binary size still matter.
