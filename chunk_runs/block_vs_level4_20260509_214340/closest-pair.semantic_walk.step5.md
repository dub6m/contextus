# closest-pair.pdf - semantic_walk Step 5

## Chunk 0

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[1, 2]`
- Element count: `8`
- Element types: `['title', 'text', 'text', 'text', 'text', 'text', 'text', 'text']`
- Element ids: `['3233c173-587a-4510-9f21-b4acc519b4fe', 'f7929612-5876-487f-89ba-77302c354688', '6b8153d9-4f9d-477a-9c66-6f794168ec52', '13ca234b-6c24-46d6-b6b9-e09bd9797194', '93bf6751-505a-40e3-b67f-633d8960d00c', '989a2922-f52e-4f60-83f9-38178b0f2a12', '2d158e1d-667e-43a8-90e3-c8ae22f68050', '97ce0acc-6a33-4948-8a0e-b25c0ce53b8e']`
- Reason: semantic_walk threshold=0.339; split_starts=894a8eea-a1e9-4349-816d-02573e81d308

```text
Closest Pair of Points in the Plane
We consider a fundamental problem in computational geometry: Given a set of n points in the plane, ﬁnd a pair of points whose distance is smallest possible.
In this problem, the input is a list of n points P = {p1, p2, ..., pn} in the Euclidean plane where pi = (xi, yi), for each i = 1 to n.
For any two points pi, pj →P, deﬁne d(pi, pj) to be the standard Euclidean distance between them.
The problem is to ﬁnd a pair of points pi, pj →P that minimizes d(pi, pj).
To make the presentation cleaner, let us assume that no two points in P have the same x-coordinate or the same y-coordinate.
We can accomplish this by performing an appropriate rotation on the points, which preserves distances between points.
Let’s make some reasonable assumptions regarding several basic operations:
```

## Chunk 1

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[2]`
- Element count: `2`
- Element types: `['text', 'text']`
- Element ids: `['894a8eea-a1e9-4349-816d-02573e81d308', '10450c4d-d590-4e6d-819c-2dbc33105eb9']`
- Reason: semantic_walk threshold=0.339; split_starts=894a8eea-a1e9-4349-816d-02573e81d308

```text
The distance between any two points can be computed in O(1) time.
Membership in a set or list can be computed in O(1) time. We will make use of these two assumptions when computing the running time of our algorithm.
```

## Chunk 2

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[3, 4]`
- Element count: `9`
- Element types: `['title', 'text', 'text', 'text', 'text', 'text', 'text', 'text', 'text']`
- Element ids: `['9f708c1a-e99d-48c6-8232-c628e834aa4f', '1ba0e92c-e6fe-41ed-ab08-72ce9a40429d', '55c575db-a04b-4a19-8cf8-d69c0a80d1cb', '5561f627-73d3-4d5d-a52a-7f774ecce384', '8dd3811f-29b7-4f89-bb08-ef9530afa532', '41838264-4ad6-4d12-9a1e-a7b2b7ec6098', 'bd983412-a9a1-4053-8782-9c0f2953bcbd', '83ad266b-1f91-41c5-8e1e-33c9f8090936', 'd8f17077-0b6b-46ef-8b83-9448ebe62042']`
- Reason: semantic_walk threshold=0.260; split_starts=1993ceff-a5f5-4336-8298-9e163879b12b

```text
Closest Pair of Points in the Plane
It’s clear that this problem can be solved in time O(n2) by computing the distance between all distinct pairs of points in P.
Our goal here is to present an algorithm which solves the problem in time O(n log n).
The plan is to apply a use divide-and-conquer similar to the technique used in the mergesort algorithm.
ﬁnd a closest pair of points in the “left half” of P,
ﬁnd a closest pair with one point in the the left half and the other point in the right half of P,
return the pair that is the closest amongst the above three pairs
The recursive divided-and-conquer algorithm will solve the closest pair problem for a subset of points P →↑P.
The input to this recursive divide-and-conquer algorithm, denoted by Recursive ↓Closest ↓Pair, will be two lists P → x and P → y, where
```

## Chunk 3

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[4]`
- Element count: `2`
- Element types: `['text', 'text']`
- Element ids: `['1993ceff-a5f5-4336-8298-9e163879b12b', '2447d883-4235-488e-9439-f01fe33be31d']`
- Reason: semantic_walk threshold=0.260; split_starts=1993ceff-a5f5-4336-8298-9e163879b12b

```text
Note that the contents of P → x and P → y are the same as P →.
Before the initial call to Recursive ↓Closest ↓Pair, we sort the original list of points P by increasing x-coordinate to get a list Px and sort P by increasing y-coordinate to get the list Py.
```

## Chunk 4

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[5]`
- Element count: `3`
- Element types: `['title', 'text', 'text']`
- Element ids: `['4e4e5f57-bfa5-424c-aadb-b43236b29971', '1666ea78-de13-4272-baa8-f733a68ca358', 'e4e4cc5b-c753-47fb-9d8e-513c6b55ed9a']`
- Reason: semantic_walk threshold=0.227; split_starts=67a39aaf-a349-440a-b757-73df2e21cf06

```text
Closest Pair of Points in the Plane
Let us consider the design of the Recursive ↓Closest ↓Pair algorithm with input P → x and P → y.
The algorithm is given P →↑P in the form of P → x and P → y and must return a closest pair of points in P →.
```

## Chunk 5

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[5]`
- Element count: `5`
- Element types: `['formula', 'text', 'text', 'text', 'text']`
- Element ids: `['67a39aaf-a349-440a-b757-73df2e21cf06', 'bc3a8122-951d-4afd-adbd-c7dd3c932540', '5ca6c188-30fc-427b-a723-a2e0f9993f6d', '276bbcae-f1e8-40bc-a523-1086d290699c', '5bbb0471-218e-4844-9b2a-6ba045ab257e']`
- Reason: semantic_walk threshold=0.227; split_starts=67a39aaf-a349-440a-b757-73df2e21cf06

```text
Formula: Let n = |P'| = |P' subscript x | = |P' subscript y |
In the algorithm, we deﬁne the following sets.
The set Q is deﬁned to be the set of points in the ﬁrst ↔n/2↗ elements in P → x, and
the set R is deﬁned to be the set of points in the last ↘n/2≃ elements of P → x.
The set Q contains the left half of the points and R contains the right half of the points to be examined.
```

## Chunk 6

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[6]`
- Element count: `3`
- Element types: `['title', 'text', 'text']`
- Element ids: `['fdb998b7-8514-42ef-b7ec-73e91db04851', 'a9df6684-476c-4e05-9357-c26cca191fb6', 'dff36b20-6906-417e-8c6b-a71c61b12a23']`
- Reason: semantic_walk threshold=0.219; split_starts=3fa4cef8-09cf-4b92-83e5-6d1bdf5929ad

```text
Closest Pair of Points in the Plane
Using a single pass through each of P → x and P → y in time O(n), the algorithm creates the following 4 lists:
2 The list Qy, consisting of the points in Q sorted by increasing y-coordinate,
```

## Chunk 7

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[6, 7]`
- Element count: `7`
- Element types: `['text', 'text', 'text', 'text', 'text', 'text', 'text']`
- Element ids: `['3fa4cef8-09cf-4b92-83e5-6d1bdf5929ad', '24e04180-52d9-4df6-9bb1-2e90a26087c3', 'c5a1897f-6691-4ce0-8bc5-939d3a2d9918', '1d5da4bf-6baa-4d51-8a5a-4b48f3fc42a5', 'bbe5d3e7-1cd2-4852-869a-8afa4fd64368', '4de228da-f792-47d3-b580-9a0fcbfcbc21', 'e5904b42-69b0-4dd5-ad6d-09154207473f']`
- Reason: semantic_walk threshold=0.219; split_starts=3fa4cef8-09cf-4b92-83e5-6d1bdf5929ad

```text
3 The list Rx, consisting of the points in R sorted by increasing x-coordinate, and
4 The list Ry, consisting of the points in R sorted by increasing y-coordinate.
The reason these 4 lists are created is so that the algorithm can recursively call itself to ﬁnd the closest pair in Q, and the closest pair in R.
To compute the closest pair of points in Q, recursively call Recursive ↓Closest ↓Pair(Qx, Qy).
Similarly, to compute the closest pair of points in R, recursively call Recursive ↓Closest ↓Pair(Rx, Ry).
Now the algorithm needs to determine the closest pair of points with one point in Q and the other point in R and combine/compare it with the results of the two recursive calls.
We now show how this can be done. This step is analogous to the merging step in the mergesort algorithm.
```

## Chunk 8

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[8]`
- Element count: `6`
- Element types: `['title', 'text', 'text', 'text', 'text', 'text']`
- Element ids: `['63960db8-31cb-4da6-8a33-ce61ec314558', '47d51431-14e7-42a6-a230-bebf0af1163a', '5228c5dd-9a61-4a29-9f78-60da6331a90d', '10df1306-44f3-4f91-8197-3837b77b863f', 'ce0cf796-65d5-475d-9d5c-3da8b9280c50', 'cc357c07-970d-4162-b739-3ee45b4934e1']`
- Reason: semantic_walk threshold=0.147; split_starts=4b3c6a26-4ac6-4f75-8dcf-9c01c773e109

```text
Closest Pair of Points in the Plane
Our goal here is to show how to determine the closest pair of points with one point in Q and the other point in R
Suppose q→ 0 and q→ 1 are returned as a closest pair of points in Q and r→ 0 and r→ 1 are returned as a closest pair of points in R.
Let ω = min{d(q→ 0, q→ 1), d(r→ 0 , r→ 1 )}.
The algorithm needs to answer the question: Is there a pair of points q →Q, r →R such that d(q, r) < ω?
If the answer is no, then one of the pairs q→ 0, q→ 1 or r→ 0 , r→ 1 is the closest pair in P →.
```

## Chunk 9

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[8]`
- Element count: `2`
- Element types: `['text', 'text']`
- Element ids: `['4b3c6a26-4ac6-4f75-8dcf-9c01c773e109', '28bd0273-326c-4cf0-afee-856934de800d']`
- Reason: semantic_walk threshold=0.147; split_starts=4b3c6a26-4ac6-4f75-8dcf-9c01c773e109

```text
If the answer is yes, then a pair (p, q) where q →Q, r →R form a closest pair in P →, which the algorithm needs to compute.
We now proceed to show how this question can be e!ciently answered.
```

## Chunk 10

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[9]`
- Element count: `2`
- Element types: `['title', 'text']`
- Element ids: `['99b651ad-578e-4e28-b499-c049e8b5acfd', '311cfa1c-426b-4755-8951-8d20ee2d43c4']`
- Reason: semantic_walk threshold=0.285; split_starts=026279c1-c782-484e-9cd5-45f8c8357f5f

```text
Closest Pair of Points in the Plane
Let x→denote the x-coordinate of the rightmost point in Q and let L denote a vertical line given by x = x→.
```

## Chunk 11

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[9]`
- Element count: `2`
- Element types: `['text', 'text']`
- Element ids: `['026279c1-c782-484e-9cd5-45f8c8357f5f', '50b28678-2a11-470f-8b59-1ea5258a929e']`
- Reason: semantic_walk threshold=0.285; split_starts=026279c1-c782-484e-9cd5-45f8c8357f5f

```text
This line L separates Q and R.
The ﬁgure on the next slide shows the partition of L and R by the line L.
```

## Chunk 12

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[9]`
- Element count: `2`
- Element types: `['title', 'text']`
- Element ids: `['ece03d49-823b-4ca5-8323-794bbde00327', 'f72b8b5f-7078-4e8b-ade1-7ae2158ec759']`
- Reason: semantic_walk threshold=0.224; split_starts=be992fa5-b77e-4cfe-a231-edf257fcacd6

```text
Claim 5.1.
If there exists q →Q, r →R such that d(q, r) < ω, then each of q and r is within a distance ω of the line L.
```

## Chunk 13

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[9, 10]`
- Element count: `3`
- Element types: `['text', 'figure', 'text']`
- Element ids: `['be992fa5-b77e-4cfe-a231-edf257fcacd6', 'bce2aeaa-0e73-49b1-a254-8f44b1a51f1a', 'c827c931-911a-4e1c-8e62-0f4d502693c3']`
- Reason: semantic_walk threshold=0.224; split_starts=be992fa5-b77e-4cfe-a231-edf257fcacd6

```text
Note: The distance of a point and the line L is the smallest distance between the point and the line L. For example, if q = (qx, qy) →Q and L is the vertical line at x→, then the distance between q and L is x→↓qx, their horizontal distance.
Figure (figure): A diagram showing a vertical bold line dividing the image into left and right sides. Left side features several small open circles; a small pair of connected circles with a short segment is labeled δ above it. The left region is labeled Q near the bottom. The right side has a group of open circles, and is labeled R at the bottom. The vertical line has a small circle intersecting it and is annotated with the letter L along its length.. δ L Q R
Figure: The partition of P →into Q and R and the line L separating the two sets of points
```

## Chunk 14

- Strategy: `semantic_walk_trivial`
- Stability: `locked`
- Pages: `[11]`
- Element count: `1`
- Element types: `['title']`
- Element ids: `['85cb20e5-23ca-42d2-8890-dd6ad60290ff']`
- Reason: semantic_walk skipped; no internal boundaries

```text
Closest Pair of Points in the Plane
```

## Chunk 15

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[11]`
- Element count: `5`
- Element types: `['title', 'text', 'text', 'formula', 'text']`
- Element ids: `['12bf0c64-ddba-4826-9436-88651c6ba1b1', '89ee9ad9-1377-47cf-9285-be845739a0b6', '76b0a53b-2b4c-4324-a2fb-d38d07ba0f74', '003a78e8-1b80-4018-9dd2-830d7af8b76b', '27983151-f160-48ac-b881-8434746bd3fb']`
- Reason: semantic_walk threshold=0.181; split_starts=acbf7911-433e-4343-a331-de4ce4924996

```text
Proof.
Suppose q = (qx, qy) →Q, r = (rx, ry) →R exists such d(q, r) < ω.
By deﬁnition of x→, qx ⇐x→< rx which implies
Formula: x to the power of * - q subscript x le r subscript x - q subscript x le d(q,r) < delta
and
```

## Chunk 16

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[11]`
- Element count: `3`
- Element types: `['formula', 'text', 'text']`
- Element ids: `['acbf7911-433e-4343-a331-de4ce4924996', 'aac3ac34-e18f-4506-a2d5-518139c6c805', '69bc1b99-b6ce-4894-90f5-1b60b850157d']`
- Reason: semantic_walk threshold=0.181; split_starts=acbf7911-433e-4343-a331-de4ce4924996

```text
Formula: r subscript x - x to the power of * le r subscript x - q subscript x le d(q, r) < delta.
Therefore by q and r lies within a distance ω of the line L.
This claim implies that if we want to ﬁnd q and r that are “close”, we can restrict our search to the band consisting of points in P → within ω distance from the line L.
```

## Chunk 17

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[12]`
- Element count: `3`
- Element types: `['title', 'text', 'text']`
- Element ids: `['9e29bc0d-fd84-498e-add7-3e9b01508c4f', 'f5a0c62d-21db-4a8c-9eea-0b5e52736b98', '18800611-e0e8-427a-a98c-430326deb838']`
- Reason: semantic_walk found no breakpoint outliers

```text
Closest Pair of Points in the Plane
Let S ↑P →be those points that are within distance ω from L.
Let Sy denote the list S, sorted by increasing y-coordinate. Note that Sy can constructed in O(n) time using a single pass through P → y.
```

## Chunk 18

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[12]`
- Element count: `2`
- Element types: `['title', 'text']`
- Element ids: `['4bdd952c-2df5-41c2-98bb-1287990f94b0', '391a500f-b958-4791-ad44-df007bf907fa']`
- Reason: semantic_walk found no breakpoint outliers

```text
Claim 5.2.
If s, t →S has the property that d(s, t) < ω, then s and t are within 15 positions of each other in the sorted list Sy.
```

## Chunk 19

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[12]`
- Element count: `1`
- Element types: `['title']`
- Element ids: `['31d61eeb-ccae-4f74-9bfb-f3be2fcd89c5']`
- Reason: semantic_walk threshold=0.235; split_starts=b40d0fd8-87a1-42c4-9700-4e5466347fb3

```text
Proof.
```

## Chunk 20

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[12, 13]`
- Element count: `6`
- Element types: `['text', 'text', 'text', 'text', 'figure', 'text']`
- Element ids: `['b40d0fd8-87a1-42c4-9700-4e5466347fb3', '4cfb3eac-2556-446c-92f4-a019adb29fb5', '7bbbc554-90da-4ac2-9106-f088c97ea564', '0ee6964b-75e7-47f9-b8a9-8bc4a96b5fbc', 'c0e48a6f-aaa4-4be5-b4b9-511932378bd2', 'e91ed507-26fb-44b3-b0e9-3b0a6a30394d']`
- Reason: semantic_walk threshold=0.235; split_starts=b40d0fd8-87a1-42c4-9700-4e5466347fb3

```text
Consider the subset Z of the plane consisting of all points within a distance ω of the line L.
Partition Z into square boxes with sides of length ω/2.
A row of Z consists of 4 boxes
A ﬁgure illustrating this partitioning of Z is given on the next slide.
Figure (figure): A schematic diagram with a central vertical solid line and a surrounding grid of dotted lines forming rectangular blocks. Labels δ/2 appear near the top-left region and along the left edge, while δ labels appear along the bottom left and bottom right near the central axis.. δ/2 δ/2 δ δ
Figure: Partition of Z into boxes with sides of length ω/2
```

## Chunk 21

- Strategy: `semantic_walk_trivial`
- Stability: `locked`
- Pages: `[14]`
- Element count: `1`
- Element types: `['title']`
- Element ids: `['afb6d561-9200-4cb9-973f-1f6fe3cf962e']`
- Reason: semantic_walk skipped; no internal boundaries

```text
Closest Pair of Points in the Plane
```

## Chunk 22

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[14]`
- Element count: `2`
- Element types: `['title', 'text']`
- Element ids: `['09834a3b-2f36-4c4a-b0b1-92d24cdf8952', 'fd1920f2-cb70-4d7d-8816-817e32deba98']`
- Reason: semantic_walk threshold=0.143; split_starts=e0370681-b74f-4e5b-b7ef-6264fec6ce8f

```text
Proof.
It’s easy to see that no two points can lie in the same box since if they were in the same box that would imply they are both in Q or both in R and we know that two points both in Q or both in R has distance at most ω.
```

## Chunk 23

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[14]`
- Element count: `2`
- Element types: `['text', 'text']`
- Element ids: `['e0370681-b74f-4e5b-b7ef-6264fec6ce8f', '058a6ac4-e869-464a-b017-9956cafdf8f9']`
- Reason: semantic_walk threshold=0.143; split_starts=e0370681-b74f-4e5b-b7ef-6264fec6ce8f

```text
Therefore each box contains at most one point of S.
Now suppose s, t →S has property d(s, t) < ω and they are at least 16 positions in Sy with s appearing before t in Sy.
```

## Chunk 24

- Strategy: `semantic_walk_trivial`
- Stability: `locked`
- Pages: `[15]`
- Element count: `1`
- Element types: `['title']`
- Element ids: `['bd38fe52-7a55-451d-b49f-3662a493723d']`
- Reason: semantic_walk skipped; no internal boundaries

```text
Closest Pair of Points in the Plane
```

## Chunk 25

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[15]`
- Element count: `4`
- Element types: `['title', 'text', 'text', 'text']`
- Element ids: `['08eabe69-ac7c-431d-9e69-150ec47c4911', 'a46ab66d-5834-4ffe-a088-a167c7ea101a', 'a587dac2-50f0-4477-88a4-fad5e85415db', '97fffa61-7318-4597-a00a-77e404954848']`
- Reason: semantic_walk threshold=0.282; split_starts=5731e158-77c8-40c1-99ab-9f7d7153cd8f

```text
Proof.
Since at most one point of S can be in any box, there are at least 3 rows of boxes separating points s and t.
As any two points in Z separated by at least 3 rows of boxes must be of distance at least 3ω/2 apart.
Therefore d(s, t) ⇒3ω/2 > ω.
```

## Chunk 26

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[15, 16]`
- Element count: `7`
- Element types: `['text', 'text', 'text', 'text', 'text', 'text', 'text']`
- Element ids: `['5731e158-77c8-40c1-99ab-9f7d7153cd8f', 'bf979c5a-6496-475a-904f-fc152e56718d', '713a1b86-d19e-4e6e-bb75-dae56d46dd8f', '0b7d3bb2-23a5-4a96-a4ef-bd4ba403e36f', '1ef1f3f2-f05f-46c7-82c5-4dc29924776a', '31d210c3-6563-44db-9e76-2bf6950302a0', '08ca4c99-09ae-4b81-b1fc-86befa8ecca7']`
- Reason: semantic_walk threshold=0.282; split_starts=5731e158-77c8-40c1-99ab-9f7d7153cd8f

```text
But this contradicts the assumption that d(s, t) < ω.
Therefore, if s, t →S has property d(s, t) < ω then they are at most 15 positions apart in the list Sy.
This means that in order to compute the smallest distance between distinct pairs of points in S, we simply need to compute, for each s →Sy, its distance with the next 15 elements Sy.
We now state the complete algorithm for ﬁnding a pair of closest points in P.
The routine Closest ↓Pair is called with the set of points P.
This routine calls the recursive routine Recursive ↓Closest ↓Pair, which ﬁnds a closest pair of points in P.
The routine Recursive ↓Closest ↓Pair is given in the
```

## Chunk 27

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[18]`
- Element count: `4`
- Element types: `['title', 'text', 'text', 'text']`
- Element ids: `['5f81b3b3-277c-47b4-8a9e-02a6ab3a9bc0', 'f917994e-1267-45ce-9715-b5cdf3877c59', '3daad63a-8d59-4538-a354-082c0047fc60', 'd10c0930-e19e-42ad-9e48-dc827b70397f']`
- Reason: semantic_walk threshold=0.276; split_starts=41de387e-d82f-4939-8a5e-717df9d952a3

```text
Closest Pair of Points in the Plane
The initial sorting of P to obtain Px, Py requires O(n log n) time.
Let T(n) denote the time required by the recursive algorithm when |Px| = |Py| = n.
Then T(n) = 2T(n/2) + f (n), where f (n) is the amount of non-recursive work done by the the algorithm.
```

## Chunk 28

- Strategy: `semantic_walk`
- Stability: `likely_good`
- Pages: `[18]`
- Element count: `3`
- Element types: `['text', 'text', 'text']`
- Element ids: `['41de387e-d82f-4939-8a5e-717df9d952a3', '05efea84-58f1-4497-8495-9fd89f52846c', '9e7f5c38-eb09-449f-a41a-b5ca0d16801b']`
- Reason: semantic_walk threshold=0.276; split_starts=41de387e-d82f-4939-8a5e-717df9d952a3

```text
To compute f (n), we note that
lines 1-3 takes O(1) time. line 5 takes O(n) time, lines 9-13 times O(n) time (note that we don’t actually need to compute the points on L) line 15 takes O(n) time, since for each point in Sy, we do 15 distance computations. lines 17-24 takes O(1) time. herefore, f (n) →O(n), and the recurrence is the same as the one
Therefore, f (n) →O(n), and the recurrence is the same as the one for the mergesort implying that T(n) →O(n log n).
```
