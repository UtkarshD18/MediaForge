# ADR-004: YAML Profiles

## Context and Problem Statement
MediaForge needs to support editor-defined transcoding profiles (e.g. YouTube ProRes HQ, low-res proxy, H.264 social exports). Hardcoding these values or storing them in custom formats makes it difficult for users to inspect or customize parameters.

## Decision
We chose **YAML files** stored in `config/profiles/*.yaml` to declare custom profiles.

## Status
Approved

## Consequences
* **Pros**:
  * Human Readable: YAML is highly readable for video editors and developers compared to raw JSON or XML.
  * Modular: Profiles are defined as separate files in a directory, making it easy to share configs or drop new presets without changing core configs.
  * Safety: Parsed using `yaml.safe_load` in `config.py` to prevent arbitrary Python code execution.
* **Cons**:
  * Requires PyYAML library dependency. We manage this with uv packages.
