# Agentic Architecture Diagrams

This document contains the approved diagrams for the HARASS agentic red-teaming system. Each diagram presents a distinct architectural view without duplicating the same information.

## 1. Agentic Workflow

This workflow shows how HARASS evaluates each single-turn seed across AT or OR using a direct baseline, Adaptive ST, and Adaptive MT. Generated prompts must pass the axis-specific validity gate before they are submitted to the client target.

  
```mermaid
%%{init: {"theme": "default"}}%%
graph TD
    START(["Start Assessment"])
    VALIDATE_RUNTIME["Validate Self-Hosted LLM Runtime"]
    RUNTIME_READY{"Runtime ready?"}
    VALIDATE_TARGET["Validate Target Capabilities"]
    TARGET_COMPATIBLE{"Target compatible?"}
    CONFIG_FAILURE(["Configuration Failure"])

    SELECT_AXIS["Select Next Evaluation Axis"]
    RETRIEVE_SEED["Retrieve Next Seed"]
    DATASET[("Single-Turn Human Seed Dataset")]
    BASELINE[["Execute Direct-Request Baseline"]]
    RECORD_BASELINE["Record Baseline Result"]

    START --> VALIDATE_RUNTIME
    VALIDATE_RUNTIME --> RUNTIME_READY
    RUNTIME_READY -->|No| CONFIG_FAILURE
    RUNTIME_READY -->|Yes| VALIDATE_TARGET
    VALIDATE_TARGET --> TARGET_COMPATIBLE
    TARGET_COMPATIBLE -->|No| CONFIG_FAILURE
    TARGET_COMPATIBLE -->|Yes| SELECT_AXIS
    SELECT_AXIS -->|AT or OR| RETRIEVE_SEED
    DATASET -. Read seeds for selected axis .-> RETRIEVE_SEED
    RETRIEVE_SEED --> BASELINE
    BASELINE --> RECORD_BASELINE
    RECORD_BASELINE --> SELECT_MODE

    subgraph AGENT["Adaptive Red-Teaming Agent"]
        direction TD

        SELECT_MODE["Select Next Adaptive Mode"]
        PLAN_ATTEMPT["Plan Next Adaptive Attempt"]
        GENERATE_PROMPT["Request Arabic Test Prompt"]
        RECORD_PROMPT["Record Generated Prompt"]
        VALIDATE_PROMPT["Validate Generated Prompt"]
        PROMPT_VALID{"Prompt valid?"}
        RETRY_AVAILABLE{"Generation retry available?"}
        SUBMIT_PROMPT["Submit through PyRIT PromptTarget"]
        SCORE_RESPONSE["Request Axis-Specific Evaluation"]
        RECORD_EVALUATION["Record Response and Evaluation"]
        OBJECTIVE_ACHIEVED{"Evaluation objective achieved?"}
        BUDGET_REMAINING{"Target-attempt budget remaining?"}
        RECORD_ATTACK["Record AttackResult"]
        RECORD_INVALID["Record Validation-Limit Outcome"]

        SELECT_MODE -->|Adaptive ST or Adaptive MT| PLAN_ATTEMPT
        PLAN_ATTEMPT --> GENERATE_PROMPT
        RECORD_PROMPT --> VALIDATE_PROMPT
        VALIDATE_PROMPT --> PROMPT_VALID

        PROMPT_VALID -->|Valid| SUBMIT_PROMPT
        PROMPT_VALID -->|Invalid or uncertain| RETRY_AVAILABLE
        RETRY_AVAILABLE -->|Yes| GENERATE_PROMPT
        RETRY_AVAILABLE -->|No| RECORD_INVALID

        OBJECTIVE_ACHIEVED -->|Yes| RECORD_ATTACK
        OBJECTIVE_ACHIEVED -->|No| BUDGET_REMAINING
        BUDGET_REMAINING -->|Yes - Judge feedback| PLAN_ATTEMPT
        BUDGET_REMAINING -->|No| RECORD_ATTACK
    end

    subgraph SELF_HOSTED_LLM["Self-Hosted vLLM Runtime"]
        direction LR
        GENERATOR_LLM["Generator Role"]
        JUDGE_LLM["Judge Role"]
    end

    GENERATE_PROMPT -->|Generation request| GENERATOR_LLM
    GENERATOR_LLM -->|Arabic test prompt| RECORD_PROMPT

    TARGET["Client Target LLM"]
    SUBMIT_PROMPT -->|Arabic test prompt| TARGET
    TARGET -->|Target response| SCORE_RESPONSE
    SCORE_RESPONSE -->|Response and rubric| JUDGE_LLM
    JUDGE_LLM -->|Score and rationale| RECORD_EVALUATION
    RECORD_EVALUATION --> OBJECTIVE_ACHIEVED

    MODES_COMPLETED{"Both adaptive modes completed?"}
    MORE_SEEDS{"More seeds in selected axis?"}
    AXES_COMPLETED{"Both evaluation axes completed?"}

    RECORD_ATTACK --> MODES_COMPLETED
    RECORD_INVALID --> MODES_COMPLETED
    MODES_COMPLETED -->|No| SELECT_MODE
    MODES_COMPLETED -->|Yes| MORE_SEEDS
    MORE_SEEDS -->|Yes| RETRIEVE_SEED
    MORE_SEEDS -->|No| AXES_COMPLETED
    AXES_COMPLETED -->|No| SELECT_AXIS
    AXES_COMPLETED -->|Yes| AGGREGATE_RESULTS

    subgraph STORAGE["Azure SQL Persistence"]
        direction LR
        MEMORY[("PyRIT Memory")]
        RESULTS[("HARASS Application Records")]
    end

    MEMORY -. Read execution state .-> PLAN_ATTEMPT
    RECORD_EVALUATION -. Write response, score, and state .-> MEMORY
    RECORD_PROMPT -. Write prompt and provenance .-> RESULTS
    VALIDATE_PROMPT -. Write validation result .-> RESULTS
    RECORD_BASELINE -. Write baseline result .-> RESULTS
    RECORD_ATTACK -. Write adaptive result .-> RESULTS
    RECORD_INVALID -. Write terminal outcome .-> RESULTS

    AGGREGATE_RESULTS["Aggregate Assessment Results"]
    COMPLETE(["Assessment Complete"])

    RESULTS -. Read recorded results .-> AGGREGATE_RESULTS
    AGGREGATE_RESULTS --> COMPLETE
```

An invalid or uncertain generated prompt is never submitted to the target and does not consume the target-attempt budget. Human review and curated-dataset admission occur after assessment and are documented separately.

## 2. Agentic Component Diagram — Pending

Shows the static responsibilities and dependencies of the Generator, Validity Gate, PyRIT PromptTarget, client target, axis-specific Judge, PyRIT Memory, and application records.

## 3. Adaptive Single-Turn Sequence Diagram — Pending

Shows how every Adaptive ST attempt starts a fresh target conversation while Judge feedback guides the next generated attempt.

## 4. Adaptive Multi-Turn Sequence Diagram — Pending

Shows how Adaptive MT preserves one target conversation across turns while the Generator adapts each following turn from the conversation state and Judge feedback.
