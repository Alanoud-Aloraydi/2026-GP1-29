# HARASS

**Hardened Arabic Red-Teaming And Safety Shield**

**IT 496: Graduation Project-1**  
Department of Information Technology  
College of Computer and Information Sciences  
King Saud University  
First Semester 1448H — Fall 2026

---

## Overview

HARASS is a web-based project for evaluating the safety of Arabic-supporting large language models (LLMs) through safety evaluation and red teaming. It addresses two safety concerns: **Adversarial Attacks** and **Over-refusal**, across five Arabic varieties: Modern Standard Arabic (MSA), Najdi, Hijazi, Egyptian, and Levantine Arabic.

HARASS combines fixed dataset-based single-turn evaluation with **HARASS Agent**, which supports adaptive single-turn and adaptive multi-turn evaluation for both safety concerns. Model responses are assessed through automated evaluation with human-assisted validation. The project also includes **HARASS Shield**, a defensive component for evaluating model safety before and after fine-tuning under matched conditions.

## Project Goal

HARASS provides a structured framework for evaluating and comparing safety behavior in Arabic-supporting LLMs across Arabic varieties, safety concerns, and interaction settings. The evaluation considers both harmful compliance and unnecessary refusal of legitimate requests.

## Technology Stack

- **Frontend:** React, TypeScript, Node.js
- **Backend:** Python, FastAPI
- **Database:** PostgreSQL
- **LLM and Data:** PyTorch, Hugging Face Transformers, Datasets, and Hub
- **Model Serving:** vLLM
- **Agent Orchestration:** LangGraph
- **Containerization:** Docker
- **Cloud and Compute:** Render, Render Workflows, RunPod
- **External Model APIs:** OpenAI API, Anthropic API

## Running the Project

No executable software increment is available during Sprint 0.

## Supervisor

**Prof. Hend Al-Khalifa**

## Authors

Project authors are listed in the [AUTHORS](AUTHORS) file.
