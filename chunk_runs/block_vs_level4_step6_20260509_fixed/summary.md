# Step 5 Strategy Comparison

## closest-pair

### block

- LLM calls: `24` total (`14` Step 5, `10` Step 6)
- Elapsed: `215.42`s Step 5, `64.7`s Step 6
- Step 5 chunks: `19` avg elements `5.32` singletons `4`
- Step 6 chunks: `15` avg elements `6.73` singletons `1`
- Step 6 risk flags: `{'possible_internal_split': 7, 'multiple_headings_in_chunk': 4, 'singleton_text_chunk': 1}`
- Repair actions: `{'merge_orphan_support_with_next': 1, 'merge_repaired_scaffold_with_body': 1, 'merge_heading_with_next': 2}`

### semantic_walk

- LLM calls: `9` total (`0` Step 5, `9` Step 6)
- Elapsed: `18.46`s Step 5, `120.91`s Step 6
- Step 5 chunks: `29` avg elements `3.48` singletons `4`
- Step 6 chunks: `25` avg elements `4.04` singletons `0`
- Step 6 risk flags: `{'possible_internal_split': 5, 'multiple_headings_in_chunk': 5}`
- Repair actions: `{'merge_heading_with_next': 4}`

## 09-Inheritance_fowler_anth1210_24

### block

- LLM calls: `37` total (`20` Step 5, `17` Step 6)
- Elapsed: `30.34`s Step 5, `25.04`s Step 6
- Step 5 chunks: `34` avg elements `2.29` singletons `13`
- Step 6 chunks: `22` avg elements `3.55` singletons `1`
- Step 6 risk flags: `{'multiple_headings_in_chunk': 8, 'trailing_support_before_next_heading': 11, 'mixed_visual_support_candidate': 4, 'singleton_text_chunk': 1, 'heading_without_body_text': 6, 'visual_edge_support_candidate': 1}`
- Repair actions: `{'merge_heading_with_next': 6, 'merge_orphan_support_with_previous': 2, 'merge_dangling_text_with_previous': 2, 'merge_orphan_support_with_next': 1, 'merge_repaired_scaffold_with_body': 1}`

### semantic_walk

- LLM calls: `17` total (`0` Step 5, `17` Step 6)
- Elapsed: `35.39`s Step 5, `23.35`s Step 6
- Step 5 chunks: `35` avg elements `2.23` singletons `10`
- Step 6 chunks: `25` avg elements `3.12` singletons `0`
- Step 6 risk flags: `{'multiple_headings_in_chunk': 8, 'visual_edge_support_candidate': 3, 'trailing_support_before_next_heading': 12, 'heading_without_body_text': 6, 'mixed_visual_support_candidate': 2}`
- Repair actions: `{'merge_heading_with_next': 7, 'merge_dangling_text_with_previous': 2, 'merge_orphan_support_with_previous': 1}`
