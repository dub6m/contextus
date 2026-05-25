# Deterministic Ranking Diagnostics

This report explains the final deterministic package score. The old embedding-style score is kept as `legacy_score` for comparison.

## closest-definition

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00004` | `13ca234b-6c24-46d6-b6b9-e09bd9797194` | 0.7088 | 0.474 | 0.738 | 0.7738 | 1.0 | 0.5989 | 0.3333 | 0.549 | 0.3503 | 0.74 | covers 3 planned need(s), package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans | misses 2 planned need(s), open completion needs: definition:p1, definition:p2 |
| 2 | `query-cluster-package-00003` | `4b3c6a26-4ac6-4f75-8dcf-9c01c773e109` | 0.6903 | 0.6637 | 0.5549 | 0.6532 | 0.895 | 0.5163 | 0.6667 | 1.0 | 0.5392 | 0.8067 | covers 2 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | misses 3 planned need(s) |
| 3 | `query-cluster-package-00001` | `bd983412-a9a1-4053-8782-9c0f2953bcbd` | 0.6246 | 0.6871 | 0.4593 | 0.532 | 0.845 | 0.3569 | 0.3333 | 1.0 | 0.5685 | 0.92 | covers 2 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | misses 3 planned need(s), package evidence profile only weakly matches query demand |
| 4 | `query-cluster-package-00002` | `41838264-4ad6-4d12-9a1e-a7b2b7ec6098` | 0.6222 | 0.756 | 0.3695 | 0.571 | 0.895 | 0.3696 | 0.3333 | 1.0 | 0.5918 | 0.92 | covers 2 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | misses 3 planned need(s), package evidence profile only weakly matches query demand |
| 5 | `query-cluster-package-00000` | `83ad266b-1f91-41c5-8e1e-33c9f8090936` | 0.619 | 0.6618 | 0.4906 | 0.6606 | 0.9297 | 0.6863 | 0.6667 | 0.25 | 0.5036 | 0.67 | covers 4 planned need(s), assembled from strong anchors/spans | misses 1 planned need(s), open completion needs: definition:n2, definition:s, proof:reason, package evidence profile only weakly matches query demand |

### Package 1: `query-cluster-package-00004`

- Roles seen: `assumption, claim, definition, proof_setup`
- Expected roles: `definition, example, procedure, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define the problem in terms of the map: what constitutes a 'closest pair' and the objective, State the input/output format and basic notation used in the map for closest pair, Describe the algorithmic approach implied by the map for solving the problem`
- Missing sub-needs: `State known running time bounds and method to achieve them as per the map, Identify key intermediate lemmas or principles in the map that justify the approach`
- Open completion keys: `definition:p1, definition:p2`

### Package 2: `query-cluster-package-00003`

- Roles seen: `assumption, definition, procedure_step, proof_reason, proof_setup`
- Expected roles: `definition, example, procedure, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define the problem in terms of the map: what constitutes a 'closest pair' and the objective, Describe the algorithmic approach implied by the map for solving the problem`
- Missing sub-needs: `State the input/output format and basic notation used in the map for closest pair, State known running time bounds and method to achieve them as per the map, Identify key intermediate lemmas or principles in the map that justify the approach`
- Open completion keys: ``

### Package 3: `query-cluster-package-00001`

- Roles seen: `definition, procedure_step`
- Expected roles: `definition, example, procedure, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define the problem in terms of the map: what constitutes a 'closest pair' and the objective, Describe the algorithmic approach implied by the map for solving the problem`
- Missing sub-needs: `State the input/output format and basic notation used in the map for closest pair, State known running time bounds and method to achieve them as per the map, Identify key intermediate lemmas or principles in the map that justify the approach`
- Open completion keys: ``

### Package 4: `query-cluster-package-00002`

- Roles seen: `definition, procedure_step`
- Expected roles: `definition, example, procedure, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define the problem in terms of the map: what constitutes a 'closest pair' and the objective, Describe the algorithmic approach implied by the map for solving the problem`
- Missing sub-needs: `State the input/output format and basic notation used in the map for closest pair, State known running time bounds and method to achieve them as per the map, Identify key intermediate lemmas or principles in the map that justify the approach`
- Open completion keys: ``

### Package 5: `query-cluster-package-00000`

- Roles seen: `definition, procedure_step, proof_conclusion, proof_setup`
- Expected roles: `definition, example, procedure, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define the problem in terms of the map: what constitutes a 'closest pair' and the objective, State the input/output format and basic notation used in the map for closest pair, Describe the algorithmic approach implied by the map for solving the problem, State known running time bounds and method to achieve them as per the map`
- Missing sub-needs: `Identify key intermediate lemmas or principles in the map that justify the approach`
- Open completion keys: `definition:n2, definition:s, proof:reason`

## closest-procedure

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00000` | `83ad266b-1f91-41c5-8e1e-33c9f8090936` | 0.7169 | 0.878 | 0.8714 | 0.8889 | 0.92 | 0.5755 | 0.25 | 0.0 | 0.7129 | 0.5 | package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans, embedding relevance is strong enough | open completion needs: proof:reason, proof:setup, selected elements are source-order jumpy |
| 2 | `query-cluster-package-00001` | `5561f627-73d3-4d5d-a52a-7f774ecce384` | 0.6967 | 0.8427 | 0.7836 | 0.8334 | 0.945 | 0.5704 | 0.0 | 0.0 | 0.6689 | 0.7267 | package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans, embedding relevance is strong enough | open completion needs: proof:reason, proof:setup |
| 3 | `query-cluster-package-00004` | `1666ea78-de13-4272-baa8-f733a68ca358` | 0.6903 | 0.7768 | 0.7586 | 0.9001 | 0.895 | 0.5625 | 0.5 | 0.0 | 0.6014 | 0.75 | package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans | open completion needs: proof:reason, proof:setup |
| 4 | `query-cluster-package-00003` | `4b3c6a26-4ac6-4f75-8dcf-9c01c773e109` | 0.6664 | 0.5445 | 0.7567 | 0.8033 | 0.6183 | 0.5252 | 1.0 | 0.7315 | 0.4287 | 0.33 | package evidence profile matches query demand, answer evidence is near the core | open completion needs: answer:conquer, answer:divide, answer:does, answer:work, selected elements are source-order jumpy |
| 5 | `query-cluster-package-00002` | `0b7d3bb2-23a5-4a96-a4ef-bd4ba403e36f` | 0.6409 | 0.5622 | 0.746 | 0.7209 | 0.5225 | 0.5231 | 1.0 | 0.7186 | 0.4293 | 0.4793 | package evidence profile matches query demand, answer evidence is near the core | open completion needs: answer:conquer, answer:divide, answer:does, answer:work, definition:d, selected elements are source-order jumpy |

### Package 1: `query-cluster-package-00000`

- Roles seen: `procedure_step`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `proof:reason, proof:setup`

### Package 2: `query-cluster-package-00001`

- Roles seen: `definition`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `proof:reason, proof:setup`

### Package 3: `query-cluster-package-00004`

- Roles seen: `definition, procedure_step, proof_setup`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `proof:reason, proof:setup`

### Package 4: `query-cluster-package-00003`

- Roles seen: `assumption, definition, procedure_step, proof_conclusion, proof_reason, proof_setup`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `answer:conquer, answer:divide, answer:does, answer:work`

### Package 5: `query-cluster-package-00002`

- Roles seen: `assumption, claim, comparison, contradiction, definition, procedure_step, proof_conclusion, proof_reason`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `answer:conquer, answer:divide, answer:does, answer:work, definition:d`

## closest-q-r

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00001` | `c5a1897f-6691-4ce0-8bc5-939d3a2d9918` | 0.7357 | 0.6326 | 0.7391 | 0.9086 | 0.876 | 0.5328 | 1.0 | 0.782 | 0.5383 | 0.5093 | package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans | open completion needs: definition:qx, definition:qy, definition:rx, definition:ry, selected elements are source-order jumpy |
| 2 | `query-cluster-package-00000` | `1d5da4bf-6baa-4d51-8a5a-4b48f3fc42a5` | 0.7331 | 0.8439 | 0.7488 | 0.9116 | 0.7487 | 0.55 | 1.0 | 0.7318 | 0.6991 | 0.41 | package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans, embedding relevance is strong enough | open completion needs: definition:qx, definition:qy, definition:rx, definition:ry, selected elements are source-order jumpy |
| 3 | `query-cluster-package-00002` | `4de228da-f792-47d3-b580-9a0fcbfcbc21` | 0.7318 | 0.6689 | 0.7402 | 0.9086 | 0.8943 | 0.5339 | 1.0 | 0.7401 | 0.5876 | 0.3431 | package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans | open completion needs: definition:qx, definition:qy, definition:rx, definition:ry, selected elements are source-order jumpy |
| 4 | `query-cluster-package-00003` | `4b3c6a26-4ac6-4f75-8dcf-9c01c773e109` | 0.7287 | 0.6653 | 0.7406 | 0.9057 | 0.8943 | 0.5347 | 1.0 | 0.7401 | 0.561 | 0.3292 | package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans | open completion needs: definition:qx, definition:qy, definition:rx, definition:ry, selected elements are source-order jumpy |
| 5 | `query-cluster-package-00004` | `1666ea78-de13-4272-baa8-f733a68ca358` | 0.7154 | 0.6991 | 0.7524 | 0.9372 | 0.803 | 0.5612 | 0.5 | 0.5 | 0.5345 | 0.546 | package evidence profile matches query demand, answer evidence is near the core, assembled from strong anchors/spans | open completion needs: proof:reason, selected elements are source-order jumpy |

### Package 1: `query-cluster-package-00001`

- Roles seen: `assumption, claim, comparison, definition, procedure_step, proof_conclusion, proof_reason, proof_setup`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `definition:qx, definition:qy, definition:rx, definition:ry`

### Package 2: `query-cluster-package-00000`

- Roles seen: `assumption, claim, comparison, definition, procedure_step, proof_conclusion, proof_reason, proof_setup`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `definition:qx, definition:qy, definition:rx, definition:ry`

### Package 3: `query-cluster-package-00002`

- Roles seen: `assumption, claim, comparison, definition, procedure_step, proof_conclusion, proof_reason, proof_setup`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `definition:qx, definition:qy, definition:rx, definition:ry`

### Package 4: `query-cluster-package-00003`

- Roles seen: `assumption, claim, comparison, definition, procedure_step, proof_conclusion, proof_reason, proof_setup`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `definition:qx, definition:qy, definition:rx, definition:ry`

### Package 5: `query-cluster-package-00004`

- Roles seen: `claim, comparison, definition, procedure_step, proof_setup`
- Expected roles: `procedure`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `proof:reason`

## closest-above-three-pairs

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00002` | `4b3c6a26-4ac6-4f75-8dcf-9c01c773e109` | 0.6572 | 0.7365 | 0.6148 | 0.6709 | 0.895 | 0.2149 | 0.6667 | 1.0 | 0.6069 | 0.8067 | assembled from strong anchors/spans, completion ledger mostly closed | misses 3 planned need(s), support need is not clearly satisfied |
| 2 | `query-cluster-package-00001` | `83ad266b-1f91-41c5-8e1e-33c9f8090936` | 0.6154 | 0.7888 | 0.5003 | 0.6385 | 1.0 | 0.1506 | 0.5 | 1.0 | 0.6133 | 0.636 | assembled from strong anchors/spans, completion ledger mostly closed | misses 3 planned need(s), support need is not clearly satisfied, package evidence profile only weakly matches query demand |
| 3 | `query-cluster-package-00000` | `bd983412-a9a1-4053-8782-9c0f2953bcbd` | 0.5885 | 0.804 | 0.4076 | 0.5803 | 0.845 | 0.1373 | 0.3333 | 1.0 | 0.6662 | 0.92 | assembled from strong anchors/spans, completion ledger mostly closed, embedding relevance is strong enough | misses 3 planned need(s), support need is not clearly satisfied, package evidence profile only weakly matches query demand |
| 4 | `query-cluster-package-00003` | `0b7d3bb2-23a5-4a96-a4ef-bd4ba403e36f` | 0.5707 | 0.6065 | 0.6122 | 0.6674 | 0.5225 | 0.2321 | 0.8333 | 0.9135 | 0.4686 | 0.4793 | completion ledger mostly closed | misses 3 planned need(s), open completion needs: definition:d, selected elements are source-order jumpy, support need is not clearly satisfied |
| 5 | `query-cluster-package-00004` | `276bbcae-f1e8-40bc-a523-1086d290699c` | 0.5599 | 0.5847 | 0.3965 | 0.5667 | 1.0 | 0.1468 | 0.5 | 1.0 | 0.4451 | 0.6167 | assembled from strong anchors/spans, completion ledger mostly closed | misses 3 planned need(s), support need is not clearly satisfied, package evidence profile only weakly matches query demand |

### Package 1: `query-cluster-package-00002`

- Roles seen: `assumption, definition, procedure_step, proof_reason, proof_setup`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the three candidate pair types evaluated in the cross-step of the divide-and-conquer closest pair: (a) closest pair in Q, (b) closest pair in R, and (c) closest cross-pair with one point in Q and one in R., Provide the definitions/notation for Q, R, and the cross-set of pairs used to form the final three-pair consideration., Describe how these three pairs are used to determine the eventual closest pair in P, referencing the comparison with ω and the line L partition concept as applicable.`
- Open completion keys: ``

### Package 2: `query-cluster-package-00001`

- Roles seen: `definition, procedure_step, proof_conclusion`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the three candidate pair types evaluated in the cross-step of the divide-and-conquer closest pair: (a) closest pair in Q, (b) closest pair in R, and (c) closest cross-pair with one point in Q and one in R., Provide the definitions/notation for Q, R, and the cross-set of pairs used to form the final three-pair consideration., Describe how these three pairs are used to determine the eventual closest pair in P, referencing the comparison with ω and the line L partition concept as applicable.`
- Open completion keys: ``

### Package 3: `query-cluster-package-00000`

- Roles seen: `definition, procedure_step`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the three candidate pair types evaluated in the cross-step of the divide-and-conquer closest pair: (a) closest pair in Q, (b) closest pair in R, and (c) closest cross-pair with one point in Q and one in R., Provide the definitions/notation for Q, R, and the cross-set of pairs used to form the final three-pair consideration., Describe how these three pairs are used to determine the eventual closest pair in P, referencing the comparison with ω and the line L partition concept as applicable.`
- Open completion keys: ``

### Package 4: `query-cluster-package-00003`

- Roles seen: `assumption, claim, comparison, contradiction, definition, procedure_step, proof_conclusion, proof_reason`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the three candidate pair types evaluated in the cross-step of the divide-and-conquer closest pair: (a) closest pair in Q, (b) closest pair in R, and (c) closest cross-pair with one point in Q and one in R., Provide the definitions/notation for Q, R, and the cross-set of pairs used to form the final three-pair consideration., Describe how these three pairs are used to determine the eventual closest pair in P, referencing the comparison with ω and the line L partition concept as applicable.`
- Open completion keys: `definition:d`

### Package 5: `query-cluster-package-00004`

- Roles seen: `assumption, claim, comparison, definition, procedure_step`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the three candidate pair types evaluated in the cross-step of the divide-and-conquer closest pair: (a) closest pair in Q, (b) closest pair in R, and (c) closest cross-pair with one point in Q and one in R., Provide the definitions/notation for Q, R, and the cross-set of pairs used to form the final three-pair consideration., Describe how these three pairs are used to determine the eventual closest pair in P, referencing the comparison with ω and the line L partition concept as applicable.`
- Open completion keys: ``

## closest-contradiction

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00004` | `69bc1b99-b6ce-4894-90f5-1b60b850157d` | 0.632 | 0.2432 | 0.705 | 0.7674 | 0.851 | 0.5346 | 0.75 | 0.4739 | 0.1197 | 0.5417 | covers 2 planned need(s), answer evidence is near the core, assembled from strong anchors/spans | misses 1 planned need(s), open completion needs: answer:assumption, answer:contradicts, answer:does, definition:band, definition:d, selected elements are source-order jumpy |
| 2 | `query-cluster-package-00001` | `5731e158-77c8-40c1-99ab-9f7d7153cd8f` | 0.5961 | 0.3509 | 0.7112 | 0.7439 | 0.617 | 0.3336 | 0.5 | 0.7921 | 0.2159 | 0.425 | covers 1 planned need(s), answer evidence is near the core | misses 2 planned need(s), open completion needs: answer:does, answer:proof, definition:d, selected elements are source-order jumpy, support need is not clearly satisfied |
| 3 | `query-cluster-package-00003` | `1993ceff-a5f5-4336-8298-9e163879b12b` | 0.4422 | 0.1509 | 0.4763 | 0.3137 | 0.82 | 0.1102 | 0.25 | 0.5 | 0.1056 | 0.92 | assembled from strong anchors/spans | misses 3 planned need(s), open completion needs: proof:setup, support need is not clearly satisfied, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 4 | `query-cluster-package-00002` | `97ce0acc-6a33-4948-8a0e-b25c0ce53b8e` | 0.4356 | 0.2253 | 0.4188 | 0.375 | 0.845 | 0.3198 | 0.5 | 0.2857 | 0.146 | 0.58 | covers 1 planned need(s), assembled from strong anchors/spans | misses 2 planned need(s), open completion needs: answer:assumption, answer:contradicts, answer:does, answer:proof, proof:conclusion, support need is not clearly satisfied, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 5 | `query-cluster-package-00000` | `12bf0c64-ddba-4826-9436-88651c6ba1b1` | 0.3454 | 0.025 | 0.2495 | 0.3194 | 0.82 | 0.0763 | 0.25 | 0.1667 | 0.1779 | 0.92 | assembled from strong anchors/spans | misses 3 planned need(s), open completion needs: answer:assumption, answer:contradicts, answer:does, proof:conclusion, proof:reason, support need is not clearly satisfied, token/noise pressure is high, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |

### Package 1: `query-cluster-package-00004`

- Roles seen: `assumption, claim, definition, procedure_step, proof_conclusion, proof_reason, proof_setup, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, quote_evidence, support, theorem_application`
- Covered sub-needs: `Identify the assumption that is claimed contradicted (e.g., d(q,r) ≥ ω or that s,t∈S have d(s,t)≥ω)., Show the mechanism that ties the assumption to the contradiction via the band/box partition and proximity in Sy.`
- Missing sub-needs: `Explain how the existence of a closer cross-border pair (q∈Q, r∈R) leads to contradiction with proximity/box arguments.`
- Open completion keys: `answer:assumption, answer:contradicts, answer:does, definition:band, definition:d, definition:delta, definition:q, definition:qx, definition:qy, definition:r, definition:rx, definition:ry, definition:t, definition:x`

### Package 2: `query-cluster-package-00001`

- Roles seen: `comparison, contradiction, definition, proof_conclusion, proof_reason, proof_setup`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, quote_evidence, support, theorem_application`
- Covered sub-needs: `Identify the assumption that is claimed contradicted (e.g., d(q,r) ≥ ω or that s,t∈S have d(s,t)≥ω).`
- Missing sub-needs: `Explain how the existence of a closer cross-border pair (q∈Q, r∈R) leads to contradiction with proximity/box arguments., Show the mechanism that ties the assumption to the contradiction via the band/box partition and proximity in Sy.`
- Open completion keys: `answer:does, answer:proof, definition:d`

### Package 3: `query-cluster-package-00003`

- Roles seen: `definition, proof_reason`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, quote_evidence, support, theorem_application`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the assumption that is claimed contradicted (e.g., d(q,r) ≥ ω or that s,t∈S have d(s,t)≥ω)., Explain how the existence of a closer cross-border pair (q∈Q, r∈R) leads to contradiction with proximity/box arguments., Show the mechanism that ties the assumption to the contradiction via the band/box partition and proximity in Sy.`
- Open completion keys: `proof:setup`

### Package 4: `query-cluster-package-00002`

- Roles seen: `definition, procedure_step, proof_reason, proof_setup`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, quote_evidence, support, theorem_application`
- Covered sub-needs: `Identify the assumption that is claimed contradicted (e.g., d(q,r) ≥ ω or that s,t∈S have d(s,t)≥ω).`
- Missing sub-needs: `Explain how the existence of a closer cross-border pair (q∈Q, r∈R) leads to contradiction with proximity/box arguments., Show the mechanism that ties the assumption to the contradiction via the band/box partition and proximity in Sy.`
- Open completion keys: `answer:assumption, answer:contradicts, answer:does, answer:proof, proof:conclusion`

### Package 5: `query-cluster-package-00000`

- Roles seen: `definition, proof_setup`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, quote_evidence, support, theorem_application`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the assumption that is claimed contradicted (e.g., d(q,r) ≥ ω or that s,t∈S have d(s,t)≥ω)., Explain how the existence of a closer cross-border pair (q∈Q, r∈R) leads to contradiction with proximity/box arguments., Show the mechanism that ties the assumption to the contradiction via the band/box partition and proximity in Sy.`
- Open completion keys: `answer:assumption, answer:contradicts, answer:does, proof:conclusion, proof:reason`

## closest-strip-nearby

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00004` | `0b7d3bb2-23a5-4a96-a4ef-bd4ba403e36f` | 0.6167 | 0.5726 | 0.7642 | 0.5934 | 0.5225 | 0.5155 | 1.0 | 0.6921 | 0.4149 | 0.4793 | package evidence profile matches query demand | open completion needs: answer:nearby, answer:only, answer:strip, definition:d, definition:strip, selected elements are source-order jumpy |
| 2 | `query-cluster-package-00003` | `63960db8-31cb-4da6-8a33-ce61ec314558` | 0.5313 | 0.573 | 0.8217 | 0.2609 | 0.364 | 0.5263 | 1.0 | 0.543 | 0.4847 | 0.24 | package evidence profile matches query demand | open completion needs: answer:nearby, answer:only, answer:strip, definition:band, definition:strip, selected elements are source-order jumpy, answer evidence is not direct to the core, assembly relies too much on weak/patchy attachments |
| 3 | `query-cluster-package-00000` | `9f708c1a-e99d-48c6-8232-c628e834aa4f` | 0.3386 | 0.3415 | 0.0 | 0.2609 | 0.508 | 0.5526 | 0.3333 | 0.1299 | 0.4628 | 0.5 |  | open completion needs: answer:nearby, answer:only, answer:strip, definition:strip, proof:conclusion, selected elements are source-order jumpy, package evidence profile only weakly matches query demand, answer evidence is not direct to the core, assembly relies too much on weak/patchy attachments |
| 4 | `query-cluster-package-00001` | `4e4e5f57-bfa5-424c-aadb-b43236b29971` | 0.3377 | 0.3392 | 0.0 | 0.2609 | 0.508 | 0.5556 | 0.3333 | 0.1299 | 0.4607 | 0.38 |  | open completion needs: answer:nearby, answer:only, answer:strip, definition:strip, proof:conclusion, selected elements are source-order jumpy, package evidence profile only weakly matches query demand, answer evidence is not direct to the core, assembly relies too much on weak/patchy attachments |
| 5 | `query-cluster-package-00002` | `fdb998b7-8514-42ef-b7ec-73e91db04851` | 0.3305 | 0.352 | 0.0 | 0.2609 | 0.508 | 0.5526 | 0.3333 | 0.1299 | 0.472 | 0.32 |  | open completion needs: answer:nearby, answer:only, answer:strip, definition:strip, proof:conclusion, selected elements are source-order jumpy, package evidence profile only weakly matches query demand, answer evidence is not direct to the core, assembly relies too much on weak/patchy attachments |

### Package 1: `query-cluster-package-00004`

- Roles seen: `assumption, claim, comparison, contradiction, definition, procedure_step, proof_conclusion, proof_reason`
- Expected roles: `proof_conclusion, proof_reason`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `answer:nearby, answer:only, answer:strip, definition:d, definition:strip, term:strip`

### Package 2: `query-cluster-package-00003`

- Roles seen: `claim, definition, proof_conclusion, proof_reason, proof_setup`
- Expected roles: `proof_conclusion, proof_reason`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `answer:nearby, answer:only, answer:strip, definition:band, definition:strip, term:strip`

### Package 3: `query-cluster-package-00000`

- Roles seen: `assumption, definition, proof_setup`
- Expected roles: `proof_conclusion, proof_reason`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `answer:nearby, answer:only, answer:strip, definition:strip, proof:conclusion, proof:reason, term:strip`

### Package 4: `query-cluster-package-00001`

- Roles seen: `assumption, definition, proof_setup`
- Expected roles: `proof_conclusion, proof_reason`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `answer:nearby, answer:only, answer:strip, definition:strip, proof:conclusion, proof:reason, term:strip`

### Package 5: `query-cluster-package-00002`

- Roles seen: `assumption, definition, proof_setup`
- Expected roles: `proof_conclusion, proof_reason`
- Covered sub-needs: ``
- Missing sub-needs: ``
- Open completion keys: `answer:nearby, answer:only, answer:strip, definition:strip, proof:conclusion, proof:reason, term:strip`

## inheritance-punnett

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00000` | `30434f75-28ad-4dcc-a5f6-756e79d04b7a` | 0.6974 | 0.6036 | 0.4782 | 0.6247 | 0.935 | 0.7141 | 0.5 | 1.0 | 0.522 | 0.75 | covers 4 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | package evidence profile only weakly matches query demand |
| 2 | `query-cluster-package-00001` | `90bb1f2f-0d0b-44c5-b1c6-7004cb951a29` | 0.6955 | 0.5755 | 0.4801 | 0.6634 | 0.86 | 0.7318 | 0.6667 | 1.0 | 0.43 | 0.835 | covers 4 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | package evidence profile only weakly matches query demand |
| 3 | `query-cluster-package-00002` | `3674a9c5-b9b5-4e8d-9e8f-625e528cbe6c` | 0.6929 | 0.7071 | 0.476 | 0.643 | 0.86 | 0.6587 | 0.5 | 1.0 | 0.5329 | 0.92 | covers 4 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | package evidence profile only weakly matches query demand |
| 4 | `query-cluster-package-00003` | `57a0345c-65d9-4028-8b6c-5ebc86bbfced` | 0.6503 | 0.6717 | 0.4406 | 0.5744 | 0.97 | 0.5506 | 0.5 | 1.0 | 0.5393 | 0.57 | covers 3 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | misses 1 planned need(s), package evidence profile only weakly matches query demand |
| 5 | `query-cluster-package-00004` | `7d8adb24-2379-4e87-a54c-95707d67c138` | 0.6008 | 0.3674 | 0.377 | 0.4643 | 0.91 | 0.6411 | 0.3333 | 1.0 | 0.2575 | 0.6133 | covers 4 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | package evidence profile only weakly matches query demand, answer evidence is not direct to the core |

### Package 1: `query-cluster-package-00000`

- Roles seen: `claim, comparison, definition, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify Punnett square as a diagrammatic tool for combining parental gametes to yield offspring genotypes, Link Punnett square to genotype–phenotype outcomes and dominance relationships (dominant/recessive) as illustrated in the map, Reference example configurations in the document map (2x2 with B/b or C/D; 4x4 dihybrid) to ground the illustration, Explain what the Punnett square illustrates in terms of inheritance principles from the map (segregation, independent assortment, alleles as combinations)`
- Missing sub-needs: ``
- Open completion keys: ``

### Package 2: `query-cluster-package-00001`

- Roles seen: `claim, comparison, definition, proof_reason, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify Punnett square as a diagrammatic tool for combining parental gametes to yield offspring genotypes, Link Punnett square to genotype–phenotype outcomes and dominance relationships (dominant/recessive) as illustrated in the map, Reference example configurations in the document map (2x2 with B/b or C/D; 4x4 dihybrid) to ground the illustration, Explain what the Punnett square illustrates in terms of inheritance principles from the map (segregation, independent assortment, alleles as combinations)`
- Missing sub-needs: ``
- Open completion keys: ``

### Package 3: `query-cluster-package-00002`

- Roles seen: `claim, comparison, definition, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify Punnett square as a diagrammatic tool for combining parental gametes to yield offspring genotypes, Link Punnett square to genotype–phenotype outcomes and dominance relationships (dominant/recessive) as illustrated in the map, Reference example configurations in the document map (2x2 with B/b or C/D; 4x4 dihybrid) to ground the illustration, Explain what the Punnett square illustrates in terms of inheritance principles from the map (segregation, independent assortment, alleles as combinations)`
- Missing sub-needs: ``
- Open completion keys: ``

### Package 4: `query-cluster-package-00003`

- Roles seen: `claim, comparison, definition, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify Punnett square as a diagrammatic tool for combining parental gametes to yield offspring genotypes, Link Punnett square to genotype–phenotype outcomes and dominance relationships (dominant/recessive) as illustrated in the map, Explain what the Punnett square illustrates in terms of inheritance principles from the map (segregation, independent assortment, alleles as combinations)`
- Missing sub-needs: `Reference example configurations in the document map (2x2 with B/b or C/D; 4x4 dihybrid) to ground the illustration`
- Open completion keys: ``

### Package 5: `query-cluster-package-00004`

- Roles seen: `definition, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify Punnett square as a diagrammatic tool for combining parental gametes to yield offspring genotypes, Link Punnett square to genotype–phenotype outcomes and dominance relationships (dominant/recessive) as illustrated in the map, Reference example configurations in the document map (2x2 with B/b or C/D; 4x4 dihybrid) to ground the illustration, Explain what the Punnett square illustrates in terms of inheritance principles from the map (segregation, independent assortment, alleles as combinations)`
- Missing sub-needs: ``
- Open completion keys: ``

## inheritance-meiosis-figure

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00000` | `cf7fefc9-528a-4ab6-93cc-d486fb83addd` | 0.7531 | 0.816 | 0.5254 | 0.7211 | 0.995 | 0.8298 | 0.6 | 1.0 | 0.5967 | 0.636 | covers 2 planned need(s), answer evidence is near the core, assembled from strong anchors/spans, completion ledger mostly closed |  |
| 2 | `query-cluster-package-00001` | `8952226e-21e2-4901-b8af-c18b961a9d49` | 0.743 | 0.8288 | 0.4962 | 0.6394 | 0.945 | 0.8298 | 0.6 | 1.0 | 0.696 | 0.852 | covers 2 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed, embedding relevance is strong enough | package evidence profile only weakly matches query demand |
| 3 | `query-cluster-package-00002` | `2c540cb5-6022-46b6-bd1b-42fcc41efb86` | 0.7216 | 0.7027 | 0.4872 | 0.6102 | 1.0 | 0.8298 | 0.6 | 1.0 | 0.5415 | 0.7429 | covers 2 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | package evidence profile only weakly matches query demand |
| 4 | `query-cluster-package-00003` | `ba059811-2313-4133-be94-3708bc4e9222` | 0.5478 | 0.5459 | 0.4909 | 0.3573 | 0.8 | 0.1378 | 0.4 | 1.0 | 0.4212 | 0.92 | assembled from strong anchors/spans, completion ledger mostly closed | misses 2 planned need(s), package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 5 | `query-cluster-package-00004` | `8a7cd725-1296-4ee0-85d0-b8c0a7d71632` | 0.4599 | 0.6175 | 0.4119 | 0.0819 | 0.845 | 0.0672 | 0.2 | 1.0 | 0.5499 | 0.58 | assembled from strong anchors/spans, completion ledger mostly closed | misses 2 planned need(s), support need is not clearly satisfied, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |

### Package 1: `query-cluster-package-00000`

- Roles seen: `definition, proof_reason, proof_setup, support`
- Expected roles: `composition_bound, procedure, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify the evidence that the figure starts from a diploid cell and ends with four haploid cells., Describe the sequential steps shown in meiosis I and II in the figure and the resulting chromosome/allele behavior.`
- Missing sub-needs: ``
- Open completion keys: ``

### Package 2: `query-cluster-package-00001`

- Roles seen: `claim, definition, proof_reason, proof_setup, support`
- Expected roles: `composition_bound, procedure, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify the evidence that the figure starts from a diploid cell and ends with four haploid cells., Describe the sequential steps shown in meiosis I and II in the figure and the resulting chromosome/allele behavior.`
- Missing sub-needs: ``
- Open completion keys: ``

### Package 3: `query-cluster-package-00002`

- Roles seen: `definition, proof_reason, proof_setup, support`
- Expected roles: `composition_bound, procedure, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify the evidence that the figure starts from a diploid cell and ends with four haploid cells., Describe the sequential steps shown in meiosis I and II in the figure and the resulting chromosome/allele behavior.`
- Missing sub-needs: ``
- Open completion keys: ``

### Package 4: `query-cluster-package-00003`

- Roles seen: `proof_reason, support`
- Expected roles: `composition_bound, procedure, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the evidence that the figure starts from a diploid cell and ends with four haploid cells., Describe the sequential steps shown in meiosis I and II in the figure and the resulting chromosome/allele behavior.`
- Open completion keys: ``

### Package 5: `query-cluster-package-00004`

- Roles seen: `condition`
- Expected roles: `composition_bound, procedure, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify the evidence that the figure starts from a diploid cell and ends with four haploid cells., Describe the sequential steps shown in meiosis I and II in the figure and the resulting chromosome/allele behavior.`
- Open completion keys: ``

## inheritance-dna-unwinding

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00002` | `903420c9-37c4-40a7-8935-a76b94781541` | 0.755 | 0.7553 | 0.6828 | 0.804 | 0.8 | 0.6749 | 0.75 | 1.0 | 0.5844 | 0.58 | covers 2 planned need(s), answer evidence is near the core, assembled from strong anchors/spans, completion ledger mostly closed | misses 1 planned need(s) |
| 2 | `query-cluster-package-00003` | `5c881cc7-ae53-4404-a88a-e159a9d7287d` | 0.744 | 0.7448 | 0.6445 | 0.8016 | 0.79 | 0.6738 | 0.75 | 1.0 | 0.5886 | 0.58 | covers 2 planned need(s), answer evidence is near the core, assembled from strong anchors/spans, completion ledger mostly closed | misses 1 planned need(s) |
| 3 | `query-cluster-package-00000` | `2c51abd0-a1e0-4e0b-b332-13265cb9de9c` | 0.5591 | 0.9 | 0.2157 | 0.5821 | 0.97 | 0.5956 | 0.25 | 0.4189 | 0.6903 | 0.285 | covers 3 planned need(s), assembled from strong anchors/spans, embedding relevance is strong enough | open completion needs: definition:t, proof:reason, selected elements are source-order jumpy, package evidence profile only weakly matches query demand |
| 4 | `query-cluster-package-00001` | `9366ae0a-a7a7-4119-ad7c-891e0f4bd8f2` | 0.541 | 0.8299 | 0.2327 | 0.5342 | 0.97 | 0.5183 | 0.25 | 0.4189 | 0.6145 | 0.42 | covers 3 planned need(s), assembled from strong anchors/spans | open completion needs: definition:t, proof:reason, selected elements are source-order jumpy, package evidence profile only weakly matches query demand |
| 5 | `query-cluster-package-00004` | `c09a9c9d-1109-49c6-a1ec-be997279709f` | 0.5312 | 0.805 | 0.2653 | 0.5 | 0.825 | 0.5185 | 0.25 | 0.4189 | 0.5811 | 0.625 | covers 3 planned need(s), assembled from strong anchors/spans | open completion needs: definition:t, proof:reason, package evidence profile only weakly matches query demand |

### Package 1: `query-cluster-package-00002`

- Roles seen: `claim, procedure_step, proof_reason, support`
- Expected roles: `description, proof_reason, proof_setup, support`
- Covered sub-needs: `Describe components shown in the unwinding diagram (strands, backbone, base-pair rungs, nucleotides)., Identify whether the diagram indicates parent DNA and strand separation (unwinding) and any labeling (panels, B/Labeled strands).`
- Missing sub-needs: `Locate diagram that depicts DNA unwinding in the document map.`
- Open completion keys: ``

### Package 2: `query-cluster-package-00003`

- Roles seen: `claim, procedure_step, proof_reason, support`
- Expected roles: `description, proof_reason, proof_setup, support`
- Covered sub-needs: `Describe components shown in the unwinding diagram (strands, backbone, base-pair rungs, nucleotides)., Identify whether the diagram indicates parent DNA and strand separation (unwinding) and any labeling (panels, B/Labeled strands).`
- Missing sub-needs: `Locate diagram that depicts DNA unwinding in the document map.`
- Open completion keys: ``

### Package 3: `query-cluster-package-00000`

- Roles seen: `procedure_step, support`
- Expected roles: `description, proof_reason, proof_setup, support`
- Covered sub-needs: `Locate diagram that depicts DNA unwinding in the document map., Describe components shown in the unwinding diagram (strands, backbone, base-pair rungs, nucleotides)., Identify whether the diagram indicates parent DNA and strand separation (unwinding) and any labeling (panels, B/Labeled strands).`
- Missing sub-needs: ``
- Open completion keys: `definition:t, proof:reason`

### Package 4: `query-cluster-package-00001`

- Roles seen: `support`
- Expected roles: `description, proof_reason, proof_setup, support`
- Covered sub-needs: `Locate diagram that depicts DNA unwinding in the document map., Describe components shown in the unwinding diagram (strands, backbone, base-pair rungs, nucleotides)., Identify whether the diagram indicates parent DNA and strand separation (unwinding) and any labeling (panels, B/Labeled strands).`
- Missing sub-needs: ``
- Open completion keys: `definition:t, proof:reason`

### Package 5: `query-cluster-package-00004`

- Roles seen: `support`
- Expected roles: `description, proof_reason, proof_setup, support`
- Covered sub-needs: `Locate diagram that depicts DNA unwinding in the document map., Describe components shown in the unwinding diagram (strands, backbone, base-pair rungs, nucleotides)., Identify whether the diagram indicates parent DNA and strand separation (unwinding) and any labeling (panels, B/Labeled strands).`
- Missing sub-needs: ``
- Open completion keys: `definition:t, proof:reason`

## inheritance-sickle-map

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00000` | `83e0e7dc-9bb0-41c0-affa-0943d092955d` | 0.6192 | 0.9228 | 0.3037 | 0.5191 | 0.82 | 0.4593 | 0.3333 | 1.0 | 0.7419 | 0.92 | covers 3 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed, embedding relevance is strong enough | misses 2 planned need(s), package evidence profile only weakly matches query demand |
| 2 | `query-cluster-package-00003` | `11291337-ce01-4485-b0c3-2b3b3f82bd48` | 0.6153 | 0.8606 | 0.3289 | 0.4471 | 0.935 | 0.6344 | 0.5 | 1.0 | 0.6188 | 0.4333 | covers 4 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | misses 1 planned need(s), selected elements are source-order jumpy, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 3 | `query-cluster-package-00004` | `7d8adb24-2379-4e87-a54c-95707d67c138` | 0.6005 | 0.4248 | 0.4516 | 0.5256 | 0.96 | 0.4123 | 0.3333 | 1.0 | 0.3006 | 0.556 | covers 3 planned need(s), assembled from strong anchors/spans, completion ledger mostly closed | misses 2 planned need(s), package evidence profile only weakly matches query demand |
| 4 | `query-cluster-package-00001` | `cf7fefc9-528a-4ab6-93cc-d486fb83addd` | 0.5436 | 0.5619 | 0.4977 | 0.2624 | 0.995 | 0.2271 | 0.6667 | 1.0 | 0.3531 | 0.585 | assembled from strong anchors/spans, completion ledger mostly closed | misses 5 planned need(s), package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 5 | `query-cluster-package-00002` | `ba059811-2313-4133-be94-3708bc4e9222` | 0.4858 | 0.4359 | 0.3847 | 0.2022 | 0.8 | 0.1507 | 0.3333 | 1.0 | 0.2932 | 0.92 | assembled from strong anchors/spans, completion ledger mostly closed | misses 5 planned need(s), package evidence profile only weakly matches query demand, answer evidence is not direct to the core |

### Package 1: `query-cluster-package-00000`

- Roles seen: `comparison, proof_reason, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify malarial environment as defined in the map and its relation to sickle cell gene frequency, Explain how sickle cell alleles (C/D? in map) relate to malaria adaptation, Summarize the inferred implications for population health in the malaria-sickle cell context per the map`
- Missing sub-needs: `Describe biocultural and evolutionary implications as per map, Provide evidence lines from the map that connect genotype frequencies to malaria environment`
- Open completion keys: ``

### Package 2: `query-cluster-package-00003`

- Roles seen: `comparison, definition, proof_reason, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Identify malarial environment as defined in the map and its relation to sickle cell gene frequency, Explain how sickle cell alleles (C/D? in map) relate to malaria adaptation, Describe biocultural and evolutionary implications as per map, Summarize the inferred implications for population health in the malaria-sickle cell context per the map`
- Missing sub-needs: `Provide evidence lines from the map that connect genotype frequencies to malaria environment`
- Open completion keys: ``

### Package 3: `query-cluster-package-00004`

- Roles seen: `definition, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Explain how sickle cell alleles (C/D? in map) relate to malaria adaptation, Provide evidence lines from the map that connect genotype frequencies to malaria environment, Summarize the inferred implications for population health in the malaria-sickle cell context per the map`
- Missing sub-needs: `Identify malarial environment as defined in the map and its relation to sickle cell gene frequency, Describe biocultural and evolutionary implications as per map`
- Open completion keys: ``

### Package 4: `query-cluster-package-00001`

- Roles seen: `definition, proof_reason, proof_setup, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify malarial environment as defined in the map and its relation to sickle cell gene frequency, Explain how sickle cell alleles (C/D? in map) relate to malaria adaptation, Describe biocultural and evolutionary implications as per map, Provide evidence lines from the map that connect genotype frequencies to malaria environment, Summarize the inferred implications for population health in the malaria-sickle cell context per the map`
- Open completion keys: ``

### Package 5: `query-cluster-package-00002`

- Roles seen: `proof_reason, support`
- Expected roles: `definition, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: ``
- Missing sub-needs: `Identify malarial environment as defined in the map and its relation to sickle cell gene frequency, Explain how sickle cell alleles (C/D? in map) relate to malaria adaptation, Describe biocultural and evolutionary implications as per map, Provide evidence lines from the map that connect genotype frequencies to malaria environment, Summarize the inferred implications for population health in the malaria-sickle cell context per the map`
- Open completion keys: ``

## inheritance-mitosis-meiosis

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00004` | `67455ddd-c064-4b40-8e9a-25d71b4a9a24` | 0.7313 | 0.7826 | 0.6027 | 0.7233 | 0.92 | 0.8043 | 0.5714 | 0.6892 | 0.5985 | 0.6933 | covers 4 planned need(s), answer evidence is near the core, assembled from strong anchors/spans | open completion needs: definition:d |
| 2 | `query-cluster-package-00001` | `5f72cd66-ec93-448d-81d9-1e4f130622b0` | 0.7177 | 0.7278 | 0.5372 | 0.6792 | 1.0 | 0.7781 | 0.5714 | 0.6892 | 0.6615 | 0.7429 | covers 4 planned need(s), assembled from strong anchors/spans, embedding relevance is strong enough | open completion needs: definition:d |
| 3 | `query-cluster-package-00002` | `3d8d62f2-5c81-4713-b633-16a00107d130` | 0.6745 | 0.7035 | 0.4639 | 0.6199 | 1.0 | 0.7134 | 0.5714 | 0.6892 | 0.6221 | 0.7267 | covers 4 planned need(s), assembled from strong anchors/spans, embedding relevance is strong enough | open completion needs: definition:d, package evidence profile only weakly matches query demand |
| 4 | `query-cluster-package-00000` | `1e3d4d46-85e8-467a-b454-971608ff14d6` | 0.4323 | 0.5008 | 0.3574 | 0.3793 | 0.845 | 0.1749 | 0.1429 | 0.0 | 0.6619 | 0.92 | covers 1 planned need(s), assembled from strong anchors/spans, embedding relevance is strong enough | misses 3 planned need(s), open completion needs: proof:reason, proof:setup, support need is not clearly satisfied, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 5 | `query-cluster-package-00003` | `2c540cb5-6022-46b6-bd1b-42fcc41efb86` | 0.3966 | 0.5208 | 0.3169 | 0.2717 | 0.845 | 0.1749 | 0.1429 | 0.0 | 0.5873 | 0.92 | covers 1 planned need(s), assembled from strong anchors/spans | misses 3 planned need(s), open completion needs: proof:reason, proof:setup, support need is not clearly satisfied, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |

### Package 1: `query-cluster-package-00004`

- Roles seen: `definition, proof_reason, proof_setup, support`
- Expected roles: `comparison, definition, example, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Define mitosis vs meiosis using document terms and outcomes., Describe chromosome behavior and genetic events distinguishing the two processes., Outline typical stage sequence and structural features for mitosis and meiosis provided in map, Identify outcomes in terms of genetic variation and cell type produced.`
- Missing sub-needs: ``
- Open completion keys: `definition:d`

### Package 2: `query-cluster-package-00001`

- Roles seen: `definition, proof_reason, proof_setup, support`
- Expected roles: `comparison, definition, example, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Define mitosis vs meiosis using document terms and outcomes., Describe chromosome behavior and genetic events distinguishing the two processes., Outline typical stage sequence and structural features for mitosis and meiosis provided in map, Identify outcomes in terms of genetic variation and cell type produced.`
- Missing sub-needs: ``
- Open completion keys: `definition:d`

### Package 3: `query-cluster-package-00002`

- Roles seen: `definition, proof_reason, proof_setup, support`
- Expected roles: `comparison, definition, example, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Define mitosis vs meiosis using document terms and outcomes., Describe chromosome behavior and genetic events distinguishing the two processes., Outline typical stage sequence and structural features for mitosis and meiosis provided in map, Identify outcomes in terms of genetic variation and cell type produced.`
- Missing sub-needs: ``
- Open completion keys: `definition:d`

### Package 4: `query-cluster-package-00000`

- Roles seen: `definition`
- Expected roles: `comparison, definition, example, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Define mitosis vs meiosis using document terms and outcomes.`
- Missing sub-needs: `Describe chromosome behavior and genetic events distinguishing the two processes., Outline typical stage sequence and structural features for mitosis and meiosis provided in map, Identify outcomes in terms of genetic variation and cell type produced.`
- Open completion keys: `proof:reason, proof:setup`

### Package 5: `query-cluster-package-00003`

- Roles seen: `definition`
- Expected roles: `comparison, definition, example, procedure, proof_conclusion, proof_reason, proof_setup, support`
- Covered sub-needs: `Define mitosis vs meiosis using document terms and outcomes.`
- Missing sub-needs: `Describe chromosome behavior and genetic events distinguishing the two processes., Outline typical stage sequence and structural features for mitosis and meiosis provided in map, Identify outcomes in terms of genetic variation and cell type produced.`
- Open completion keys: `proof:reason, proof:setup`

## inheritance-evolution-table

| Rank | Package | Core | Final | Legacy | Profile | Direct | Assembly | Plan | Roles | Completion | Relevance | Coherence | Why | Concerns |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `query-cluster-package-00000` | `ff3ff6e5-4fd5-49eb-b243-ad9ae374e956` | 0.6112 | 0.7958 | 0.4721 | 0.6638 | 0.945 | 0.6373 | 0.25 | 0.1486 | 0.5575 | 0.852 | covers 3 planned need(s), assembled from strong anchors/spans | open completion needs: definition:rows, proof:reason, proof:setup, package evidence profile only weakly matches query demand |
| 2 | `query-cluster-package-00003` | `4a280e02-b110-4ca9-ba8a-b66565d17566` | 0.5645 | 0.6403 | 0.3753 | 0.4414 | 0.895 | 0.5493 | 0.5 | 0.5 | 0.4837 | 0.92 | covers 2 planned need(s), assembled from strong anchors/spans | misses 1 planned need(s), open completion needs: proof:reason, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 3 | `query-cluster-package-00001` | `8c0aa646-66d3-412c-9233-61cdf9551399` | 0.5519 | 0.6864 | 0.3142 | 0.4664 | 0.87 | 0.5493 | 0.5 | 0.5 | 0.5463 | 0.75 | covers 2 planned need(s), assembled from strong anchors/spans | misses 1 planned need(s), open completion needs: proof:reason, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 4 | `query-cluster-package-00002` | `cf237c37-1e0c-4ef1-ace2-9021261af4b3` | 0.531 | 0.69 | 0.4147 | 0.3885 | 0.845 | 0.4143 | 0.5 | 0.5 | 0.5595 | 0.75 | covers 1 planned need(s), assembled from strong anchors/spans | misses 2 planned need(s), open completion needs: proof:reason, package evidence profile only weakly matches query demand, answer evidence is not direct to the core |
| 5 | `query-cluster-package-00004` | `59159ecf-a1e9-4587-bf5f-9830f42fe36f` | 0.4245 | 0.3905 | 0.5681 | 0.2267 | 0.87 | 0.2191 | 0.25 | 0.0 | 0.2906 | 0.58 | covers 1 planned need(s), assembled from strong anchors/spans | misses 2 planned need(s), open completion needs: proof:reason, proof:setup, answer evidence is not direct to the core |

### Package 1: `query-cluster-package-00000`

- Roles seen: `comparison, definition, support`
- Expected roles: `comparison, definition, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define biological evolution using map terms and identify its observable mechanisms, Define cultural evolution using map terms and identify its observable mechanisms, Contrast mechanism differences between the two evolutions (heritability vs knowledge transmission)`
- Missing sub-needs: ``
- Open completion keys: `definition:rows, proof:reason, proof:setup`

### Package 2: `query-cluster-package-00003`

- Roles seen: `claim, definition, support`
- Expected roles: `comparison, definition, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define biological evolution using map terms and identify its observable mechanisms, Define cultural evolution using map terms and identify its observable mechanisms`
- Missing sub-needs: `Contrast mechanism differences between the two evolutions (heritability vs knowledge transmission)`
- Open completion keys: `proof:reason`

### Package 3: `query-cluster-package-00001`

- Roles seen: `claim, definition, support`
- Expected roles: `comparison, definition, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define biological evolution using map terms and identify its observable mechanisms, Define cultural evolution using map terms and identify its observable mechanisms`
- Missing sub-needs: `Contrast mechanism differences between the two evolutions (heritability vs knowledge transmission)`
- Open completion keys: `proof:reason`

### Package 4: `query-cluster-package-00002`

- Roles seen: `claim, definition`
- Expected roles: `comparison, definition, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define cultural evolution using map terms and identify its observable mechanisms`
- Missing sub-needs: `Define biological evolution using map terms and identify its observable mechanisms, Contrast mechanism differences between the two evolutions (heritability vs knowledge transmission)`
- Open completion keys: `proof:reason`

### Package 5: `query-cluster-package-00004`

- Roles seen: `comparison, definition`
- Expected roles: `comparison, definition, proof_conclusion, proof_reason, proof_setup`
- Covered sub-needs: `Define biological evolution using map terms and identify its observable mechanisms`
- Missing sub-needs: `Define cultural evolution using map terms and identify its observable mechanisms, Contrast mechanism differences between the two evolutions (heritability vs knowledge transmission)`
- Open completion keys: `proof:reason, proof:setup`
