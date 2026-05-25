# Retrieval Representation Comparison

- Cases: `12`
- Collections: `1`

## Summary

### query_proposition_profile_reranked

- hit@1 / hit@3: `11` / `11`
- hit@3 rate: `0.9167`
- mean best-hit rank: `1.33`
- misses: `1`

## Cases

### closest-definition

- Family: `definition`
- Document: `closest-pair`
- Prompt: What is the closest pair problem?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `2.1302` expected `2/2`
  - Item: `query-cluster-package-00004`
  - Source elements: `['13ca234b-6c24-46d6-b6b9-e09bd9797194']`
  - Context: `['f7929612-5876-487f-89ba-77302c354688', '6b8153d9-4f9d-477a-9c66-6f794168ec52', '93bf6751-505a-40e3-b67f-633d8960d00c', '5561f627-73d3-4d5d-a52a-7f774ecce384', '8dd3811f-29b7-4f89-bb08-ef9530afa532', '41838264-4ad6-4d12-9a1e-a7b2b7ec6098', '83ad266b-1f91-41c5-8e1e-33c9f8090936', 'd8f17077-0b6b-46ef-8b83-9448ebe62042']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | f7929612-5876-487f-89ba-77302c354688] We consider a fundamental problem in computational geometry: Given a set of n points in the plane, ﬁnd a pair of points whose distance is smallest possible. [Cluster | 6b8153d9-4f9d-477a-9c66-6f794168ec52] In this problem, the input is a list of n points P = {p1, p2,...
- Rank `2` score `2.092` expected `2/2`
  - Item: `query-cluster-package-00000`
  - Source elements: `['83ad266b-1f91-41c5-8e1e-33c9f8090936']`
  - Context: `['97ce0acc-6a33-4948-8a0e-b25c0ce53b8e', '9f708c1a-e99d-48c6-8232-c628e834aa4f', '1ba0e92c-e6fe-41ed-ab08-72ce9a40429d', '55c575db-a04b-4a19-8cf8-d69c0a80d1cb', '5561f627-73d3-4d5d-a52a-7f774ecce384', '41838264-4ad6-4d12-9a1e-a7b2b7ec6098', 'd8f17077-0b6b-46ef-8b83-9448ebe62042', 'e4e4cc5b-c753-47fb-9d8e-513c6b55ed9a']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Completion | 97ce0acc-6a33-4948-8a0e-b25c0ce53b8e] Let’s make some reasonable assumptions regarding several basic operations: [Cluster | 9f708c1a-e99d-48c6-8232-c628e834aa4f] Closest Pair of Points in the Plane [Cluster | 1ba0e92c-e6fe-41ed-ab08-72ce9a40429d] It’s clear that this problem can be solved in time O(n2)...
- Rank `3` score `1.9931` expected `2/2`
  - Item: `query-cluster-package-00002`
  - Source elements: `['41838264-4ad6-4d12-9a1e-a7b2b7ec6098']`
  - Context: `['8dd3811f-29b7-4f89-bb08-ef9530afa532', 'bd983412-a9a1-4053-8782-9c0f2953bcbd', '83ad266b-1f91-41c5-8e1e-33c9f8090936']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 8dd3811f-29b7-4f89-bb08-ef9530afa532] ﬁnd a closest pair of points in the “left half” of P, [Core | 41838264-4ad6-4d12-9a1e-a7b2b7ec6098] ﬁnd a closest pair with one point in the the left half and the other point in the right half of P, [Cluster | bd983412-a9a1-4053-8782-9c0f2953bcbd] return the pair that...

### closest-procedure

- Family: `procedure`
- Document: `closest-pair`
- Prompt: How does the divide-and-conquer closest pair algorithm work?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `4.3799` expected `3/3`
  - Item: `query-cluster-package-00001`
  - Source elements: `['5561f627-73d3-4d5d-a52a-7f774ecce384']`
  - Context: `['55c575db-a04b-4a19-8cf8-d69c0a80d1cb', '83ad266b-1f91-41c5-8e1e-33c9f8090936', 'd8f17077-0b6b-46ef-8b83-9448ebe62042']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 55c575db-a04b-4a19-8cf8-d69c0a80d1cb] Our goal here is to present an algorithm which solves the problem in time O(n log n). [Core | 5561f627-73d3-4d5d-a52a-7f774ecce384] The plan is to apply a use divide-and-conquer similar to the technique used in the mergesort algorithm. [Cluster | 83ad266b-1f91-41c5-8e...
- Rank `2` score `3.8347` expected `3/3`
  - Item: `query-cluster-package-00004`
  - Source elements: `['1666ea78-de13-4272-baa8-f733a68ca358']`
  - Context: `['83ad266b-1f91-41c5-8e1e-33c9f8090936', 'd8f17077-0b6b-46ef-8b83-9448ebe62042', '2447d883-4235-488e-9439-f01fe33be31d', 'e4e4cc5b-c753-47fb-9d8e-513c6b55ed9a']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 83ad266b-1f91-41c5-8e1e-33c9f8090936] The recursive divided-and-conquer algorithm will solve the closest pair problem for a subset of points P →↑P. [Cluster | d8f17077-0b6b-46ef-8b83-9448ebe62042] The input to this recursive divide-and-conquer algorithm, denoted by Recursive ↓Closest ↓Pair, will be two li...
- Rank `3` score `2.5248` expected `3/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['83ad266b-1f91-41c5-8e1e-33c9f8090936']`
  - Context: `['41838264-4ad6-4d12-9a1e-a7b2b7ec6098', 'e4e4cc5b-c753-47fb-9d8e-513c6b55ed9a']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 41838264-4ad6-4d12-9a1e-a7b2b7ec6098] ﬁnd a closest pair with one point in the the left half and the other point in the right half of P, [Core | 83ad266b-1f91-41c5-8e1e-33c9f8090936] The recursive divided-and-conquer algorithm will solve the closest pair problem for a subset of points P →↑P. [Cluster | e4...

### closest-q-r

- Family: `comparison`
- Document: `closest-pair`
- Prompt: How are Q and R used in the recursive closest pair algorithm?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `2.064` expected `3/3`
  - Item: `query-cluster-package-00004`
  - Source elements: `['1666ea78-de13-4272-baa8-f733a68ca358']`
  - Context: `['83ad266b-1f91-41c5-8e1e-33c9f8090936', 'd8f17077-0b6b-46ef-8b83-9448ebe62042', '2447d883-4235-488e-9439-f01fe33be31d', 'e4e4cc5b-c753-47fb-9d8e-513c6b55ed9a', '4de228da-f792-47d3-b580-9a0fcbfcbc21']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 83ad266b-1f91-41c5-8e1e-33c9f8090936] The recursive divided-and-conquer algorithm will solve the closest pair problem for a subset of points P →↑P. [Cluster | d8f17077-0b6b-46ef-8b83-9448ebe62042] The input to this recursive divide-and-conquer algorithm, denoted by Recursive ↓Closest ↓Pair, will be two li...
- Rank `2` score `2.0185` expected `3/3`
  - Item: `query-cluster-package-00003`
  - Source elements: `['4b3c6a26-4ac6-4f75-8dcf-9c01c773e109']`
  - Context: `['13ca234b-6c24-46d6-b6b9-e09bd9797194', '276bbcae-f1e8-40bc-a523-1086d290699c', '24e04180-52d9-4df6-9bb1-2e90a26087c3', 'c5a1897f-6691-4ce0-8bc5-939d3a2d9918', '1d5da4bf-6baa-4d51-8a5a-4b48f3fc42a5', 'bbe5d3e7-1cd2-4852-869a-8afa4fd64368', '4de228da-f792-47d3-b580-9a0fcbfcbc21', '5228c5dd-9a61-4a29-9f78-60da6331a90d', '10df1306-44f3-4f91-8197-3837b77b863f', 'ce0cf796-65d5-475d-9d5c-3da8b9280c50', 'cc357c07-970d-4162-b739-3ee45b4934e1', 'aac3ac34-e18f-4506-a2d5-518139c6c805', 'f5a0c62d-21db-4a8c-9eea-0b5e52736b98']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Completion | 13ca234b-6c24-46d6-b6b9-e09bd9797194] For any two points pi, pj →P, deﬁne d(pi, pj) to be the standard Euclidean distance between them. [Completion | 276bbcae-f1e8-40bc-a523-1086d290699c] the set R is deﬁned to be the set of points in the last ↘n/2≃ elements of P → x. [Cluster | 24e04180-52d9-4df6-9bb1...
- Rank `3` score `2.0166` expected `3/3`
  - Item: `query-cluster-package-00002`
  - Source elements: `['4de228da-f792-47d3-b580-9a0fcbfcbc21']`
  - Context: `['13ca234b-6c24-46d6-b6b9-e09bd9797194', '276bbcae-f1e8-40bc-a523-1086d290699c', '24e04180-52d9-4df6-9bb1-2e90a26087c3', 'c5a1897f-6691-4ce0-8bc5-939d3a2d9918', '1d5da4bf-6baa-4d51-8a5a-4b48f3fc42a5', 'bbe5d3e7-1cd2-4852-869a-8afa4fd64368', '47d51431-14e7-42a6-a230-bebf0af1163a', '5228c5dd-9a61-4a29-9f78-60da6331a90d', '10df1306-44f3-4f91-8197-3837b77b863f', 'ce0cf796-65d5-475d-9d5c-3da8b9280c50', '4b3c6a26-4ac6-4f75-8dcf-9c01c773e109', 'aac3ac34-e18f-4506-a2d5-518139c6c805', 'f5a0c62d-21db-4a8c-9eea-0b5e52736b98']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Completion | 13ca234b-6c24-46d6-b6b9-e09bd9797194] For any two points pi, pj →P, deﬁne d(pi, pj) to be the standard Euclidean distance between them. [Completion | 276bbcae-f1e8-40bc-a523-1086d290699c] the set R is deﬁned to be the set of points in the last ↘n/2≃ elements of P → x. [Cluster | 24e04180-52d9-4df6-9bb1...

### closest-above-three-pairs

- Family: `reference`
- Document: `closest-pair`
- Prompt: What are the above three pairs in the closest pair algorithm?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `4.5549` expected `3/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['bd983412-a9a1-4053-8782-9c0f2953bcbd']`
  - Context: `['41838264-4ad6-4d12-9a1e-a7b2b7ec6098']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 41838264-4ad6-4d12-9a1e-a7b2b7ec6098] ﬁnd a closest pair with one point in the the left half and the other point in the right half of P, [Core | bd983412-a9a1-4053-8782-9c0f2953bcbd] return the pair that is the closest amongst the above three pairs
- Rank `2` score `4.3072` expected `3/3`
  - Item: `query-cluster-package-00004`
  - Source elements: `['276bbcae-f1e8-40bc-a523-1086d290699c']`
  - Context: `['41838264-4ad6-4d12-9a1e-a7b2b7ec6098', 'bd983412-a9a1-4053-8782-9c0f2953bcbd', '5ca6c188-30fc-427b-a723-a2e0f9993f6d', '5bbb0471-218e-4844-9b2a-6ba045ab257e', 'bbe5d3e7-1cd2-4852-869a-8afa4fd64368', '4de228da-f792-47d3-b580-9a0fcbfcbc21']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 41838264-4ad6-4d12-9a1e-a7b2b7ec6098] ﬁnd a closest pair with one point in the the left half and the other point in the right half of P, [Cluster | bd983412-a9a1-4053-8782-9c0f2953bcbd] return the pair that is the closest amongst the above three pairs [Cluster | 5ca6c188-30fc-427b-a723-a2e0f9993f6d] The s...
- Rank `3` score `2.2519` expected `0/3`
  - Item: `query-cluster-package-00002`
  - Source elements: `['4b3c6a26-4ac6-4f75-8dcf-9c01c773e109']`
  - Context: `['5228c5dd-9a61-4a29-9f78-60da6331a90d', 'ce0cf796-65d5-475d-9d5c-3da8b9280c50', 'cc357c07-970d-4162-b739-3ee45b4934e1']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 5228c5dd-9a61-4a29-9f78-60da6331a90d] Suppose q→ 0 and q→ 1 are returned as a closest pair of points in Q and r→ 0 and r→ 1 are returned as a closest pair of points in R. [Cluster | ce0cf796-65d5-475d-9d5c-3da8b9280c50] The algorithm needs to answer the question: Is there a pair of points q →Q, r →R such...

### closest-contradiction

- Family: `reference`
- Document: `closest-pair`
- Prompt: Why does the proof say this contradicts the assumption?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `3.413` expected `3/3`
  - Item: `query-cluster-package-00001`
  - Source elements: `['5731e158-77c8-40c1-99ab-9f7d7153cd8f']`
  - Context: `['f5a0c62d-21db-4a8c-9eea-0b5e52736b98', 'a587dac2-50f0-4477-88a4-fad5e85415db', '97fffa61-7318-4597-a00a-77e404954848', '3daad63a-8d59-4538-a354-082c0047fc60']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Completion | f5a0c62d-21db-4a8c-9eea-0b5e52736b98] Let S ↑P →be those points that are within distance ω from L. [Cluster | a587dac2-50f0-4477-88a4-fad5e85415db] As any two points in Z separated by at least 3 rows of boxes must be of distance at least 3ω/2 apart. [Cluster | 97fffa61-7318-4597-a00a-77e404954848] Ther...
- Rank `2` score `1.5993` expected `0/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['12bf0c64-ddba-4826-9436-88651c6ba1b1']`
  - Context: `['85cb20e5-23ca-42d2-8890-dd6ad60290ff']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 85cb20e5-23ca-42d2-8890-dd6ad60290ff] Closest Pair of Points in the Plane [Core | 12bf0c64-ddba-4826-9436-88651c6ba1b1] Proof.
- Rank `3` score `0.9012` expected `1/3`
  - Item: `query-cluster-package-00004`
  - Source elements: `['69bc1b99-b6ce-4894-90f5-1b60b850157d']`
  - Context: `['10df1306-44f3-4f91-8197-3837b77b863f', '12bf0c64-ddba-4826-9436-88651c6ba1b1', '89ee9ad9-1377-47cf-9285-be845739a0b6', 'acbf7911-433e-4343-a331-de4ce4924996', 'aac3ac34-e18f-4506-a2d5-518139c6c805', 'f5a0c62d-21db-4a8c-9eea-0b5e52736b98', '18800611-e0e8-427a-a98c-430326deb838', '4bdd952c-2df5-41c2-98bb-1287990f94b0', '391a500f-b958-4791-ad44-df007bf907fa']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Completion | 10df1306-44f3-4f91-8197-3837b77b863f] Let ω = min{d(q→ 0, q→ 1), d(r→ 0 , r→ 1 )}. [Cluster | 12bf0c64-ddba-4826-9436-88651c6ba1b1] Proof. [Cluster | 89ee9ad9-1377-47cf-9285-be845739a0b6] Suppose q = (qx, qy) →Q, r = (rx, ry) →R exists such d(q, r) < ω. [Cluster | acbf7911-433e-4343-a331-de4ce4924996]...

### closest-strip-nearby

- Family: `citation`
- Document: `closest-pair`
- Prompt: Why can only nearby points in the strip be closest?
- Failure bucket: `retrieval_language_mismatch`

#### query_proposition_profile_reranked

- Best hit rank: `5`
- hit@1 / hit@3: `False` / `False`

- Rank `1` score `0.9471` expected `0/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['9f708c1a-e99d-48c6-8232-c628e834aa4f']`
  - Context: `['989a2922-f52e-4f60-83f9-38178b0f2a12']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Completion | 989a2922-f52e-4f60-83f9-38178b0f2a12] To make the presentation cleaner, let us assume that no two points in P have the same x-coordinate or the same y-coordinate. [Core | 9f708c1a-e99d-48c6-8232-c628e834aa4f] Closest Pair of Points in the Plane
- Rank `2` score `0.9471` expected `0/3`
  - Item: `query-cluster-package-00001`
  - Source elements: `['4e4e5f57-bfa5-424c-aadb-b43236b29971']`
  - Context: `['989a2922-f52e-4f60-83f9-38178b0f2a12']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Completion | 989a2922-f52e-4f60-83f9-38178b0f2a12] To make the presentation cleaner, let us assume that no two points in P have the same x-coordinate or the same y-coordinate. [Core | 4e4e5f57-bfa5-424c-aadb-b43236b29971] Closest Pair of Points in the Plane
- Rank `3` score `0.9471` expected `0/3`
  - Item: `query-cluster-package-00002`
  - Source elements: `['fdb998b7-8514-42ef-b7ec-73e91db04851']`
  - Context: `['989a2922-f52e-4f60-83f9-38178b0f2a12']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Completion | 989a2922-f52e-4f60-83f9-38178b0f2a12] To make the presentation cleaner, let us assume that no two points in P have the same x-coordinate or the same y-coordinate. [Core | fdb998b7-8514-42ef-b7ec-73e91db04851] Closest Pair of Points in the Plane

### inheritance-punnett

- Family: `visual-support`
- Document: `09-Inheritance_fowler_anth1210_24`
- Prompt: What does the Punnett square illustrate?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `1.3111` expected `3/3`
  - Item: `query-cluster-package-00001`
  - Source elements: `['90bb1f2f-0d0b-44c5-b1c6-7004cb951a29']`
  - Context: `['843508c0-b4b1-400d-a422-970bf5ff0244', 'a8805533-9c12-4d7b-89ef-d81827d48d09', '30434f75-28ad-4dcc-a5f6-756e79d04b7a', '3674a9c5-b9b5-4e8d-9e8f-625e528cbe6c']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 843508c0-b4b1-400d-a422-970bf5ff0244] Heredity Punnet Square [Cluster | a8805533-9c12-4d7b-89ef-d81827d48d09] Figure (figure): A 3x3 grid-like diagram showing eye color variants (brown and blue). Top row has Brown eye variant and Blue eye variant; left column displays Brown eye variant; center shows two B...
- Rank `2` score `1.0113` expected `3/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['30434f75-28ad-4dcc-a5f6-756e79d04b7a']`
  - Context: `['361893d7-c45b-4374-9429-e3dcbdf7118c', '5697b313-5a56-4477-889a-73f51726e46c', '843508c0-b4b1-400d-a422-970bf5ff0244', '90bb1f2f-0d0b-44c5-b1c6-7004cb951a29', 'a4c211f4-8627-4138-8b44-97108796c166', '3674a9c5-b9b5-4e8d-9e8f-625e528cbe6c']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 361893d7-c45b-4374-9429-e3dcbdf7118c] Heredity Punnett Square [Cluster | 5697b313-5a56-4477-889a-73f51726e46c] Figure (figure): A dihybrid cross diagram with parental genotypes YYRR and yyrr, P Generation, F1 Generation with YyRr, a 4×4 Punnett square with gametes YR, yR, Yr, yr, and F2 Generation showing...
- Rank `3` score `1.0087` expected `3/3`
  - Item: `query-cluster-package-00003`
  - Source elements: `['57a0345c-65d9-4028-8b6c-5ebc86bbfced']`
  - Context: `['843508c0-b4b1-400d-a422-970bf5ff0244', '30434f75-28ad-4dcc-a5f6-756e79d04b7a', 'a4c211f4-8627-4138-8b44-97108796c166', '3674a9c5-b9b5-4e8d-9e8f-625e528cbe6c']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Core | 57a0345c-65d9-4028-8b6c-5ebc86bbfced] Heredity Punnett Square [Cluster | 843508c0-b4b1-400d-a422-970bf5ff0244] Heredity Punnet Square [Cluster | 30434f75-28ad-4dcc-a5f6-756e79d04b7a] Heredity Punnett Square [Cluster | a4c211f4-8627-4138-8b44-97108796c166] About 16 genes control eye color in humans. Even a di...

### inheritance-meiosis-figure

- Family: `visual-support`
- Document: `09-Inheritance_fowler_anth1210_24`
- Prompt: What does the figure show about meiosis producing haploid cells?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `4.8407` expected `3/3`
  - Item: `query-cluster-package-00002`
  - Source elements: `['2c540cb5-6022-46b6-bd1b-42fcc41efb86']`
  - Context: `['1e3d4d46-85e8-467a-b454-971608ff14d6', '67455ddd-c064-4b40-8e9a-25d71b4a9a24', '5f72cd66-ec93-448d-81d9-1e4f130622b0', '69493784-4662-497d-9af2-d474b5426e1a', 'cf7fefc9-528a-4ab6-93cc-d486fb83addd', '3d8d62f2-5c81-4713-b633-16a00107d130', '8952226e-21e2-4901-b8af-c18b961a9d49']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 1e3d4d46-85e8-467a-b454-971608ff14d6] Mitosis and Meiosis [Core | 2c540cb5-6022-46b6-bd1b-42fcc41efb86] Cells [Cluster | 67455ddd-c064-4b40-8e9a-25d71b4a9a24] Figure (figure): A circular illustration showing the stages of mitosis around a central label 'MITOSIS'. Each segment depicts a cell stage (late te...
- Rank `2` score `4.7254` expected `3/3`
  - Item: `query-cluster-package-00001`
  - Source elements: `['8952226e-21e2-4901-b8af-c18b961a9d49']`
  - Context: `['5f72cd66-ec93-448d-81d9-1e4f130622b0', '69493784-4662-497d-9af2-d474b5426e1a', 'cf7fefc9-528a-4ab6-93cc-d486fb83addd', '3d8d62f2-5c81-4713-b633-16a00107d130', '00d5fbc3-a69b-4fff-8a95-52d3aa843566']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 5f72cd66-ec93-448d-81d9-1e4f130622b0] Mitosis and Meiosis [Cluster | 69493784-4662-497d-9af2-d474b5426e1a] Mitosis [Cluster | cf7fefc9-528a-4ab6-93cc-d486fb83addd] Figure (figure): A vertically arranged schematic of meiosis beginning with a diploid cell (a) that duplicates chromosomes, followed by meiosis...
- Rank `3` score `4.6705` expected `3/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['cf7fefc9-528a-4ab6-93cc-d486fb83addd']`
  - Context: `['67455ddd-c064-4b40-8e9a-25d71b4a9a24', '69493784-4662-497d-9af2-d474b5426e1a', '3d8d62f2-5c81-4713-b633-16a00107d130', '8952226e-21e2-4901-b8af-c18b961a9d49', 'ba059811-2313-4133-be94-3708bc4e9222']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 67455ddd-c064-4b40-8e9a-25d71b4a9a24] Figure (figure): A circular illustration showing the stages of mitosis around a central label 'MITOSIS'. Each segment depicts a cell stage (late telophase, cytokinesis, interphase, early prophase, prophase, prometaphase, metaphase, anaphase, early telophase) with the...

### inheritance-dna-unwinding

- Family: `visual-support`
- Document: `09-Inheritance_fowler_anth1210_24`
- Prompt: What does the DNA unwinding diagram show?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `2.1334` expected `3/3`
  - Item: `query-cluster-package-00004`
  - Source elements: `['c09a9c9d-1109-49c6-a1ec-be997279709f']`
  - Context: `['2c51abd0-a1e0-4e0b-b332-13265cb9de9c', 'c51cd5f8-0ba4-46ab-9676-a2c266c8a967']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 2c51abd0-a1e0-4e0b-b332-13265cb9de9c] Figure (figure): A schematic diagram of DNA unwinding: two vertical blue frames with hexagonal subunits and small circles, connected by horizontal colored ribbons labeled with nucleotides A, T, C, G, indicating separation into individual strands.. Parent DNA (a) Unwin...
- Rank `2` score `2.1189` expected `3/3`
  - Item: `query-cluster-package-00001`
  - Source elements: `['9366ae0a-a7a7-4119-ad7c-891e0f4bd8f2']`
  - Context: `['2c51abd0-a1e0-4e0b-b332-13265cb9de9c', 'c09a9c9d-1109-49c6-a1ec-be997279709f']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 2c51abd0-a1e0-4e0b-b332-13265cb9de9c] Figure (figure): A schematic diagram of DNA unwinding: two vertical blue frames with hexagonal subunits and small circles, connected by horizontal colored ribbons labeled with nucleotides A, T, C, G, indicating separation into individual strands.. Parent DNA (a) Unwin...
- Rank `3` score `2.1177` expected `3/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['2c51abd0-a1e0-4e0b-b332-13265cb9de9c']`
  - Context: `['5c881cc7-ae53-4404-a88a-e159a9d7287d', '9366ae0a-a7a7-4119-ad7c-891e0f4bd8f2']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 5c881cc7-ae53-4404-a88a-e159a9d7287d] Figure (figure): A vertical DNA double helix diagram with purple strands and light-colored rectangular labels containing nucleotide letters (A, T, G, C) along the backbone. A legend on the left labels Nucleotide, Base, Sugar, and Phosphate. The image includes step ann...

### inheritance-sickle-map

- Family: `visual-support`
- Document: `09-Inheritance_fowler_anth1210_24`
- Prompt: What does the malaria and sickle-cell map imply?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `2.7871` expected `3/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['83e0e7dc-9bb0-41c0-affa-0943d092955d']`
  - Context: `['e8e15ed6-2a68-4b72-89d1-2c45677f25fe']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | e8e15ed6-2a68-4b72-89d1-2c45677f25fe] Sources of Variability [Core | 83e0e7dc-9bb0-41c0-affa-0943d092955d] Figure (figure): A cropped map showing Africa with color shading representing malarial environments, overlaid by a left-side legend/table titled 'Malarial Environment' with rows for AA, AS, SS and co...
- Rank `2` score `2.3735` expected `3/3`
  - Item: `query-cluster-package-00003`
  - Source elements: `['11291337-ce01-4485-b0c3-2b3b3f82bd48']`
  - Context: `['83e0e7dc-9bb0-41c0-affa-0943d092955d', 'dd3d0938-619e-4a9d-9342-6e7491d71659', 'ff3ff6e5-4fd5-49eb-b243-ad9ae374e956']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Core | 11291337-ce01-4485-b0c3-2b3b3f82bd48] Figure (figure): A cross-sectional labeled diagram of a cell with organelles including chromosome material, nucleus, cytoplasm, ribosomes, mitochondrion, and nuclear membrane; outer boundary representing the cell membrane; labels and lines point to each structure.. Chrom...
- Rank `3` score `0.0` expected `0/3`
  - Item: `query-cluster-package-00004`
  - Source elements: `['7d8adb24-2379-4e87-a54c-95707d67c138']`
  - Context: `['57a0345c-65d9-4028-8b6c-5ebc86bbfced', '6f7e05fe-f98d-431a-920a-3e537a4c5059', '5fb18c72-8d2a-414e-b89e-bffdc43debee', 'e3ee5d9b-8fcb-4145-9135-36873c079feb', '11291337-ce01-4485-b0c3-2b3b3f82bd48']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 57a0345c-65d9-4028-8b6c-5ebc86bbfced] Heredity Punnett Square [Core | 7d8adb24-2379-4e87-a54c-95707d67c138] Genes = combinations of alleles Homozygous (alike) Heterozygous (unalike) [Cluster | 6f7e05fe-f98d-431a-920a-3e537a4c5059] Figure (figure): A large bordered rectangle contains a 2x2 grid of light gr...

### inheritance-mitosis-meiosis

- Family: `comparison`
- Document: `09-Inheritance_fowler_anth1210_24`
- Prompt: How are mitosis and meiosis different?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `1.0138` expected `3/3`
  - Item: `query-cluster-package-00002`
  - Source elements: `['3d8d62f2-5c81-4713-b633-16a00107d130']`
  - Context: `['1e3d4d46-85e8-467a-b454-971608ff14d6', '2c540cb5-6022-46b6-bd1b-42fcc41efb86', '5f72cd66-ec93-448d-81d9-1e4f130622b0', '69493784-4662-497d-9af2-d474b5426e1a', 'cf7fefc9-528a-4ab6-93cc-d486fb83addd', '8952226e-21e2-4901-b8af-c18b961a9d49']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 1e3d4d46-85e8-467a-b454-971608ff14d6] Mitosis and Meiosis [Cluster | 2c540cb5-6022-46b6-bd1b-42fcc41efb86] Cells [Cluster | 5f72cd66-ec93-448d-81d9-1e4f130622b0] Mitosis and Meiosis [Cluster | 69493784-4662-497d-9af2-d474b5426e1a] Mitosis [Cluster | cf7fefc9-528a-4ab6-93cc-d486fb83addd] Figure (figure): A...
- Rank `2` score `1.0072` expected `3/3`
  - Item: `query-cluster-package-00001`
  - Source elements: `['5f72cd66-ec93-448d-81d9-1e4f130622b0']`
  - Context: `['1e3d4d46-85e8-467a-b454-971608ff14d6', '2c540cb5-6022-46b6-bd1b-42fcc41efb86', '67455ddd-c064-4b40-8e9a-25d71b4a9a24', '69493784-4662-497d-9af2-d474b5426e1a', 'cf7fefc9-528a-4ab6-93cc-d486fb83addd', '3d8d62f2-5c81-4713-b633-16a00107d130', '8952226e-21e2-4901-b8af-c18b961a9d49']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 1e3d4d46-85e8-467a-b454-971608ff14d6] Mitosis and Meiosis [Cluster | 2c540cb5-6022-46b6-bd1b-42fcc41efb86] Cells [Cluster | 67455ddd-c064-4b40-8e9a-25d71b4a9a24] Figure (figure): A circular illustration showing the stages of mitosis around a central label 'MITOSIS'. Each segment depicts a cell stage (late...
- Rank `3` score `0.9734` expected `3/3`
  - Item: `query-cluster-package-00004`
  - Source elements: `['67455ddd-c064-4b40-8e9a-25d71b4a9a24']`
  - Context: `['6aec6014-431b-40a6-b047-f737f84244d4', 'cf7fefc9-528a-4ab6-93cc-d486fb83addd', '8952226e-21e2-4901-b8af-c18b961a9d49']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Core | 67455ddd-c064-4b40-8e9a-25d71b4a9a24] Figure (figure): A circular illustration showing the stages of mitosis around a central label 'MITOSIS'. Each segment depicts a cell stage (late telophase, cytokinesis, interphase, early prophase, prophase, prometaphase, metaphase, anaphase, early telophase) with the spi...

### inheritance-evolution-table

- Family: `comparison`
- Document: `09-Inheritance_fowler_anth1210_24`
- Prompt: How do biological evolution and cultural evolution differ?
- Failure bucket: `both_retrieved`

#### query_proposition_profile_reranked

- Best hit rank: `1`
- hit@1 / hit@3: `True` / `True`

- Rank `1` score `9.1493` expected `3/3`
  - Item: `query-cluster-package-00000`
  - Source elements: `['ff3ff6e5-4fd5-49eb-b243-ad9ae374e956']`
  - Context: `['f02a10e0-f943-4d7e-995f-4b5fd76b6fdf', 'dd3d0938-619e-4a9d-9342-6e7491d71659', 'c51cd5f8-0ba4-46ab-9676-a2c266c8a967', 'c09a9c9d-1109-49c6-a1ec-be997279709f', '32b32b4e-2fb4-4372-92d8-5194345e5416']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | f02a10e0-f943-4d7e-995f-4b5fd76b6fdf] Genetics and Evolution [Cluster | dd3d0938-619e-4a9d-9342-6e7491d71659] REQUIREMENTS FOR [Core | ff3ff6e5-4fd5-49eb-b243-ad9ae374e956] Table with columns BIOLOGICAL EVOLUTION, CULTURAL EVOLUTION. First rows show: BIOLOGICAL EVOLUTION=Variability, CULTURAL EVOLUTION=Le...
- Rank `2` score `1.3916` expected `0/3`
  - Item: `query-cluster-package-00002`
  - Source elements: `['cf237c37-1e0c-4ef1-ace2-9021261af4b3']`
  - Context: `['26c1a7db-ca69-4de0-9be6-434afbd0c7a6', '4a280e02-b110-4ca9-ba8a-b66565d17566']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 26c1a7db-ca69-4de0-9be6-434afbd0c7a6] Biocultural Model [Core | cf237c37-1e0c-4ef1-ace2-9021261af4b3] Human biological diversity is interrelated to changes in environmental conditions [Cluster | 4a280e02-b110-4ca9-ba8a-b66565d17566] One of humanity’s greatest adaptations is the development of culture
- Rank `3` score `1.2265` expected `0/3`
  - Item: `query-cluster-package-00003`
  - Source elements: `['4a280e02-b110-4ca9-ba8a-b66565d17566']`
  - Context: `['26c1a7db-ca69-4de0-9be6-434afbd0c7a6', 'cf237c37-1e0c-4ef1-ace2-9021261af4b3', '8c0aa646-66d3-412c-9233-61cdf9551399']` via `['query_cluster_consensus']`
  - Risks: `[]`
  - Preview: [Cluster | 26c1a7db-ca69-4de0-9be6-434afbd0c7a6] Biocultural Model [Cluster | cf237c37-1e0c-4ef1-ace2-9021261af4b3] Human biological diversity is interrelated to changes in environmental conditions [Cluster | 8c0aa646-66d3-412c-9233-61cdf9551399] Figure (figure): A green triangle with a red circle near the center. A...
