# Step 5 Strategy Comparison

## closest-pair

### block

- LLM calls: `25` total (`14` Step 5, `11` Step 6)
- Proposition cache: `0` hits, `0` misses
- Elapsed: `214.03`s Step 5, `121.52`s Step 6
- Step 5 chunks: `25` avg elements `4.04` singletons `7`
- Step 6 chunks: `19` avg elements `5.32` singletons `3`
- Step 6 risk flags: `{'possible_internal_split': 5, 'singleton_text_chunk': 3, 'multiple_headings_in_chunk': 4}`
- Repair actions: `{'merge_orphan_support_with_next': 1, 'merge_repaired_scaffold_with_body': 1, 'merge_orphan_support_with_previous': 1, 'merge_heading_with_next': 2, 'merge_dangling_text_with_previous': 1}`

### semantic_walk

- LLM calls: `9` total (`0` Step 5, `9` Step 6)
- Proposition cache: `0` hits, `0` misses
- Elapsed: `33.5`s Step 5, `61.02`s Step 6
- Step 5 chunks: `29` avg elements `3.48` singletons `4`
- Step 6 chunks: `25` avg elements `4.04` singletons `0`
- Step 6 risk flags: `{'possible_internal_split': 5, 'multiple_headings_in_chunk': 5}`
- Repair actions: `{'merge_heading_with_next': 4}`

### proposition_walk

- LLM calls: `23` total (`14` Step 5, `9` Step 6)
- Proposition cache: `0` hits, `98` misses
- Elapsed: `89.91`s Step 5, `61.4`s Step 6
- Step 5 chunks: `29` avg elements `3.48` singletons `4`
- Step 6 chunks: `26` avg elements `3.88` singletons `1`
- Step 6 risk flags: `{'possible_internal_split': 4, 'multiple_headings_in_chunk': 5, 'singleton_text_chunk': 1}`
- Repair actions: `{'merge_heading_with_next': 3}`

## 09-Inheritance_fowler_anth1210_24

### block

- LLM calls: `36` total (`20` Step 5, `16` Step 6)
- Proposition cache: `0` hits, `0` misses
- Elapsed: `139.83`s Step 5, `65.18`s Step 6
- Step 5 chunks: `41` avg elements `1.9` singletons `20`
- Step 6 chunks: `22` avg elements `3.55` singletons `1`
- Step 6 risk flags: `{'multiple_headings_in_chunk': 8, 'trailing_support_before_next_heading': 9, 'mixed_visual_support_candidate': 4, 'singleton_text_chunk': 1, 'heading_without_body_text': 6}`
- Repair actions: `{'merge_heading_with_next': 6, 'merge_orphan_support_with_previous': 4, 'merge_dangling_text_with_previous': 4, 'merge_orphan_support_with_next': 3, 'merge_repaired_scaffold_with_body': 2}`

### semantic_walk

- LLM calls: `16` total (`0` Step 5, `16` Step 6)
- Proposition cache: `0` hits, `0` misses
- Elapsed: `36.2`s Step 5, `31.26`s Step 6
- Step 5 chunks: `35` avg elements `2.23` singletons `10`
- Step 6 chunks: `25` avg elements `3.12` singletons `0`
- Step 6 risk flags: `{'multiple_headings_in_chunk': 8, 'visual_edge_support_candidate': 3, 'trailing_support_before_next_heading': 12, 'heading_without_body_text': 6, 'mixed_visual_support_candidate': 2}`
- Repair actions: `{'merge_heading_with_next': 7, 'merge_dangling_text_with_previous': 2, 'merge_orphan_support_with_previous': 1}`

### proposition_walk

- LLM calls: `38` total (`20` Step 5, `18` Step 6)
- Proposition cache: `0` hits, `68` misses
- Elapsed: `89.85`s Step 5, `34.17`s Step 6
- Step 5 chunks: `35` avg elements `2.23` singletons `10`
- Step 6 chunks: `25` avg elements `3.12` singletons `0`
- Step 6 risk flags: `{'multiple_headings_in_chunk': 8, 'visual_edge_support_candidate': 4, 'trailing_support_before_next_heading': 12, 'heading_without_body_text': 6, 'mixed_visual_support_candidate': 2}`
- Repair actions: `{'merge_heading_with_next': 7, 'merge_dangling_text_with_previous': 2, 'merge_orphan_support_with_previous': 1}`
