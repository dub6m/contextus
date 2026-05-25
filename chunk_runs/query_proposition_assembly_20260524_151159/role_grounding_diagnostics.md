# Role Grounding Diagnostics

Audit-only report. These labels do not change proposition selection, completion, or ranking.

## support_mismatch

- Count: `0`

## ungrounded

- Count: `9`

### `63960db8-31cb-4da6-8a33-ce61ec314558::p00`

- Document: `closest-pair`
- Element: `63960db8-31cb-4da6-8a33-ce61ec314558`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | topic title | ungrounded | P=False S=False | 0.0 | 0.0 | False | no definition-like language |

### `12bf0c64-ddba-4826-9436-88651c6ba1b1::p00`

- Document: `closest-pair`
- Element: `12bf0c64-ddba-4826-9436-88651c6ba1b1`
- Proposition: Closest Pair of Points in the Plane is the section title.
- Source overlap: `0.0`
- Kept terms: ``
- Novel terms: `closest, pair, plane, points, section, title`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Closest Pair of Points in the Plane | grounded | P=True S=False | 1.0 | 0.0 | True | definition-like language, target appears in proposition |

### `27983151-f160-48ac-b881-8434746bd3fb::p00`

- Document: `closest-pair`
- Element: `27983151-f160-48ac-b881-8434746bd3fb`
- Proposition: and
- Source overlap: `0.0`
- Kept terms: ``
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| other | connective | weak | P=False S=False | 0.0 | 0.0 | True | generic role |

### `4bdd952c-2df5-41c2-98bb-1287990f94b0::p01`

- Document: `closest-pair`
- Element: `4bdd952c-2df5-41c2-98bb-1287990f94b0`
- Proposition: If s, t ∈ S has the property that d(s, t) < ω, then s and t are within 15 positions of each other in the sorted list Sy.
- Source overlap: `0.0`
- Kept terms: ``
- Novel terms: `15, d, omega, other, positions, property, s, sorted, sy, t, within`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | Proximity in Sy when d(s,t) < ω | grounded | P=False S=False | 0.8333 | 1.0 | True | setup/condition-like language, role symbols: d, d(s,t), omega, s, sy, t, symbol overlap: d, d(s,t), omega, s, sy, t |

### `09834a3b-2f36-4c4a-b0b1-92d24cdf8952::p01`

- Document: `closest-pair`
- Element: `09834a3b-2f36-4c4a-b0b1-92d24cdf8952`
- Proposition: The section is titled Proof.
- Source overlap: `0.3333`
- Kept terms: `proof`
- Novel terms: `section, titled`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| procedure_step | Refer to Proof section in the document | ungrounded | P=False S=False | 0.5 | 0.0 | False | no procedure-like language |

### `2c540cb5-6022-46b6-bd1b-42fcc41efb86::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `2c540cb5-6022-46b6-bd1b-42fcc41efb86`
- Proposition: Mitosis and Meiosis are topics covered in the section.
- Source overlap: `0.0`
- Kept terms: ``
- Novel terms: `covered, meiosis, mitosis, section, topics`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Mitosis and Meiosis | weak | P=True S=False | 1.0 | 0.0 | False | no definition-like language, target appears in proposition |

### `69493784-4662-497d-9af2-d474b5426e1a::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `69493784-4662-497d-9af2-d474b5426e1a`
- Proposition: Meiosis
- Source overlap: `0.0`
- Kept terms: ``
- Novel terms: `meiosis`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Meiosis | weak | P=True S=False | 1.0 | 0.0 | False | no definition-like language, target appears in proposition |

### `205e45ed-3edb-4777-8418-497cb5af4269::p02`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `205e45ed-3edb-4777-8418-497cb5af4269`
- Proposition: Page header or label indicates there are requirements to be stated elsewhere.
- Source overlap: `0.1429`
- Kept terms: `requirements`
- Novel terms: `elsewhere, header, indicates, label, page, stated`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| assumption | context | ungrounded | P=False S=False | 0.0 | 0.0 | False | no setup/condition-like language |

### `dd3d0938-619e-4a9d-9342-6e7491d71659::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `dd3d0938-619e-4a9d-9342-6e7491d71659`
- Proposition: Genetics and Evolution
- Source overlap: `0.0`
- Kept terms: ``
- Novel terms: `evolution, genetics`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Genetics and Evolution | weak | P=True S=False | 1.0 | 0.0 | False | no definition-like language, target appears in proposition |

## vague_target

- Count: `3`

### `12bf0c64-ddba-4826-9436-88651c6ba1b1::p01`

- Document: `closest-pair`
- Element: `12bf0c64-ddba-4826-9436-88651c6ba1b1`
- Proposition: Proof is the section that follows.
- Source overlap: `0.3333`
- Kept terms: `proof`
- Novel terms: `follows, section`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Proof | vague_target | P=True S=True | 1.0 | 0.0 | True | definition-like language, target appears in proposition, target appears in source, target is too broad to validate confidently |

### `09834a3b-2f36-4c4a-b0b1-92d24cdf8952::p00`

- Document: `closest-pair`
- Element: `09834a3b-2f36-4c4a-b0b1-92d24cdf8952`
- Proposition: Proof.
- Source overlap: `1.0`
- Kept terms: `proof`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Proof | vague_target | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source, target is too broad to validate confidently |

### `08eabe69-ac7c-431d-9e69-150ec47c4911::p00`

- Document: `closest-pair`
- Element: `08eabe69-ac7c-431d-9e69-150ec47c4911`
- Proposition: Proof.
- Source overlap: `1.0`
- Kept terms: `proof`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Proof | vague_target | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source, target is too broad to validate confidently |

## weak

- Count: `75`

### `3233c173-587a-4510-9f21-b4acc519b4fe::p01`

- Document: `closest-pair`
- Element: `3233c173-587a-4510-9f21-b4acc519b4fe`
- Proposition: There is a fundamental problem in computational geometry described as: given a set of n points in the plane, find a pair of points whose distance is smallest possible.
- Source overlap: `0.1875`
- Kept terms: `pair, plane, points`
- Novel terms: `computational, described, distance, find, fundamental, geometry, given, n, possible, problem, smallest, whose`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | fundamental problem in computational geometry: given a set of n points in the plane, find a pair of points whose distanc | grounded | P=False S=False | 0.9231 | 1.0 | True | setup/condition-like language, role symbols: n, symbol overlap: n |

### `f7929612-5876-487f-89ba-77302c354688::p01`

- Document: `closest-pair`
- Element: `f7929612-5876-487f-89ba-77302c354688`
- Proposition: For each i from 1 to n, pi = (xi, yi) is a point in the plane.
- Source overlap: `0.2222`
- Kept terms: `n, plane`
- Novel terms: `1, i, pi, point, xi, yi`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | pi = (xi, yi) | grounded | P=True S=False | 1.0 | 1.0 | True | definition-like language, target appears in proposition, role symbols: pi, xi, yi, symbol overlap: pi, xi, yi |

### `93bf6751-505a-40e3-b67f-633d8960d00c::p00`

- Document: `closest-pair`
- Element: `93bf6751-505a-40e3-b67f-633d8960d00c`
- Proposition: The problem is to find a pair of points pi, pj in P that minimizes d(pi, pj).
- Source overlap: `0.8889`
- Kept terms: `d, minimizes, p, pair, pi, pj, points, problem`
- Novel terms: `find`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | find a pair of points that minimizes distance | weak | P=False S=False | 0.8 | 0.0 | False | no setup/condition-like language |

### `2d158e1d-667e-43a8-90e3-c8ae22f68050::p00`

- Document: `closest-pair`
- Element: `2d158e1d-667e-43a8-90e3-c8ae22f68050`
- Proposition: This can be accomplished by performing an appropriate rotation on the points.
- Source overlap: `0.8`
- Kept terms: `appropriate, performing, points, rotation`
- Novel terms: `accomplished`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | This can be accomplished by performing an appropriate rotation on the points. | weak | P=True S=False | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition |

### `97ce0acc-6a33-4948-8a0e-b25c0ce53b8e::p01`

- Document: `closest-pair`
- Element: `97ce0acc-6a33-4948-8a0e-b25c0ce53b8e`
- Proposition: We will make use of these two assumptions when computing the running time of our algorithm.
- Source overlap: `0.2`
- Kept terms: `assumptions, make`
- Novel terms: `algorithm, computing, running`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| procedure_step | We will make use of these two assumptions when computing the running time of our algorithm. | weak | P=True S=False | 1.0 | 0.0 | False | no procedure-like language, target appears in proposition |

### `894a8eea-a1e9-4349-816d-02573e81d308::p00`

- Document: `closest-pair`
- Element: `894a8eea-a1e9-4349-816d-02573e81d308`
- Proposition: The distance between any two points can be computed in O(1) time.
- Source overlap: `1.0`
- Kept terms: `1, any, between, computed, distance, o, points, time, two`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | The distance between any two points can be computed in O(1) time | weak | P=True S=True | 1.0 | 1.0 | False | no definition-like language, target appears in proposition, target appears in source, role symbols: o, symbol overlap: o |

### `10450c4d-d590-4e6d-819c-2dbc33105eb9::p00`

- Document: `closest-pair`
- Element: `10450c4d-d590-4e6d-819c-2dbc33105eb9`
- Proposition: Membership in a set or list can be computed in O(1) time.
- Source overlap: `1.0`
- Kept terms: `1, computed, list, membership, o, set, time`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Membership in a set or list can be computed in O(1) time | weak | P=True S=True | 1.0 | 1.0 | False | no definition-like language, target appears in proposition, target appears in source, role symbols: o, symbol overlap: o |

### `10450c4d-d590-4e6d-819c-2dbc33105eb9::p01`

- Document: `closest-pair`
- Element: `10450c4d-d590-4e6d-819c-2dbc33105eb9`
- Proposition: We will make use of these two assumptions when computing the running time of our algorithm.
- Source overlap: `1.0`
- Kept terms: `algorithm, assumptions, computing, make, our, running, time, two, use, we`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| proof_reason | We will make use of these two assumptions when computing the running time of our algorithm | weak | P=True S=True | 1.0 | 0.0 | False | no reasoning/derivation-like language, target appears in proposition, target appears in source |

### `9f708c1a-e99d-48c6-8232-c628e834aa4f::p00`

- Document: `closest-pair`
- Element: `9f708c1a-e99d-48c6-8232-c628e834aa4f`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Closest Pair of Points in the Plane | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `1ba0e92c-e6fe-41ed-ab08-72ce9a40429d::p00`

- Document: `closest-pair`
- Element: `1ba0e92c-e6fe-41ed-ab08-72ce9a40429d`
- Proposition: It’s clear that this problem can be solved in time O(n2) by computing the distance between all distinct pairs of points in P.
- Source overlap: `1.0`
- Kept terms: `all, between, clear, computing, distance, distinct, n2, o, p, pairs, points, problem, s, solved, time`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| proof_conclusion | The problem can be solved in O(n^2) time by computing distances for all distinct pairs in P | weak | P=False S=False | 0.75 | 0.6667 | False | no conclusion-like language, role symbols: n, o, p, symbol overlap: o, p |

### `bc3a8122-951d-4afd-adbd-c7dd3c932540::p00`

- Document: `closest-pair`
- Element: `bc3a8122-951d-4afd-adbd-c7dd3c932540`
- Proposition: In the algorithm, we deﬁne the following sets.
- Source overlap: `1.0`
- Kept terms: `algorithm, de, following, ne, sets, we`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | the following sets | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `5ca6c188-30fc-427b-a723-a2e0f9993f6d::p00`

- Document: `closest-pair`
- Element: `5ca6c188-30fc-427b-a723-a2e0f9993f6d`
- Proposition: The set Q is defined to be the set of points in the first ↔n/2↗ elements in P → x.
- Source overlap: `0.8`
- Kept terms: `2, elements, n, p, points, q, set, x`
- Novel terms: `defined, first`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Q | weak | P=True S=True | 1.0 | 1.0 | False | no definition-like language, target appears in proposition, target appears in source, role symbols: n, p, q, x, symbol overlap: n, p, q, x |

### `5ca6c188-30fc-427b-a723-a2e0f9993f6d::p01`

- Document: `closest-pair`
- Element: `5ca6c188-30fc-427b-a723-a2e0f9993f6d`
- Proposition: The set R is defined to be the set of points in the last ↘n/2≃ elements of P → x.
- Source overlap: `0.7`
- Kept terms: `2, elements, n, p, points, set, x`
- Novel terms: `defined, last, r`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | R | weak | P=True S=True | 1.0 | 1.0 | False | no definition-like language, target appears in proposition, target appears in source, role symbols: n, p, r, x, symbol overlap: n, p, r, x |

### `276bbcae-f1e8-40bc-a523-1086d290699c::p00`

- Document: `closest-pair`
- Element: `276bbcae-f1e8-40bc-a523-1086d290699c`
- Proposition: The set Q contains the left half of the points and R contains the right half of the points to be examined.
- Source overlap: `0.3333`
- Kept terms: `points, r, set`
- Novel terms: `contains, examined, half, left, q, right`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Q | weak | P=True S=False | 1.0 | 1.0 | False | no definition-like language, target appears in proposition, role symbols: q, symbol overlap: q |
| definition | R | weak | P=True S=True | 1.0 | 1.0 | False | no definition-like language, target appears in proposition, target appears in source, role symbols: r, symbol overlap: r |

### `5bbb0471-218e-4844-9b2a-6ba045ab257e::p00`

- Document: `closest-pair`
- Element: `5bbb0471-218e-4844-9b2a-6ba045ab257e`
- Proposition: The split of points into Q and R corresponds to left half and right half to be examined.
- Source overlap: `0.7778`
- Kept terms: `examined, half, left, points, q, r, right`
- Novel terms: `corresponds, split`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| assumption | split of points | weak | P=True S=False | 1.0 | 1.0 | False | no setup/condition-like language, target appears in proposition, role symbols: q, r, symbol overlap: q, r |

### `fdb998b7-8514-42ef-b7ec-73e91db04851::p00`

- Document: `closest-pair`
- Element: `fdb998b7-8514-42ef-b7ec-73e91db04851`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Closest Pair of Points in the Plane | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `a9df6684-476c-4e05-9357-c26cca191fb6::p00`

- Document: `closest-pair`
- Element: `a9df6684-476c-4e05-9357-c26cca191fb6`
- Proposition: Using a single pass through each of P → x and P → y in time O(n), the algorithm creates the following 4 lists:
- Source overlap: `1.0`
- Kept terms: `4, algorithm, creates, each, following, lists, n, o, p, pass, single, through, time, using, x, y`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| proof_setup | algorithm process | weak | P=False S=False | 0.5 | 1.0 | False | no setup/condition-like language, role symbols: n, o, p, x, y, symbol overlap: n, o, p, x, y |

### `4de228da-f792-47d3-b580-9a0fcbfcbc21::p00`

- Document: `closest-pair`
- Element: `4de228da-f792-47d3-b580-9a0fcbfcbc21`
- Proposition: The algorithm needs to determine the closest pair of points with one point in Q and the other point in R.
- Source overlap: `1.0`
- Kept terms: `algorithm, closest, determine, needs, one, other, pair, point, points, q, r`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | closest pair of points with one point in Q and the other in R | weak | P=False S=False | 1.0 | 1.0 | False | no setup/condition-like language, role symbols: one, q, r, symbol overlap: one, q, r |

### `e5904b42-69b0-4dd5-ad6d-09154207473f::p00`

- Document: `closest-pair`
- Element: `e5904b42-69b0-4dd5-ad6d-09154207473f`
- Proposition: The step is analogous to the merging step in the mergesort algorithm.
- Source overlap: `1.0`
- Kept terms: `algorithm, analogous, mergesort, merging, step`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | step analogous to merging in mergesort | weak | P=False S=False | 1.0 | 0.0 | False | no setup/condition-like language |

### `47d51431-14e7-42a6-a230-bebf0af1163a::p00`

- Document: `closest-pair`
- Element: `47d51431-14e7-42a6-a230-bebf0af1163a`
- Proposition: Our goal here is to show how to determine the closest pair of points with one point in Q and the other point in R
- Source overlap: `1.0`
- Kept terms: `closest, determine, goal, here, one, other, our, pair, point, points, q, r, show`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | determine closest pair with one in Q and one in R | weak | P=False S=False | 1.0 | 1.0 | False | no setup/condition-like language, role symbols: one, q, r, symbol overlap: one, q, r |

### `76b0a53b-2b4c-4324-a2fb-d38d07ba0f74::p01`

- Document: `closest-pair`
- Element: `76b0a53b-2b4c-4324-a2fb-d38d07ba0f74`
- Proposition: qx is less than rx with respect to the relation defined by →.
- Source overlap: `0.2857`
- Kept terms: `qx, rx`
- Novel terms: `defined, less, relation, respect, than`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| proof_conclusion | qx ⇐ rx | grounded | P=False S=False | 1.0 | 1.0 | True | conclusion-like language, role symbols: qx, rx, symbol overlap: qx, rx |

### `9e29bc0d-fd84-498e-add7-3e9b01508c4f::p00`

- Document: `closest-pair`
- Element: `9e29bc0d-fd84-498e-add7-3e9b01508c4f`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Title: Closest Pair of Points in the Plane | weak | P=False S=False | 0.8 | 0.0 | False | no definition-like language |

### `18800611-e0e8-427a-a98c-430326deb838::p01`

- Document: `closest-pair`
- Element: `18800611-e0e8-427a-a98c-430326deb838`
- Proposition: Sy can be constructed in O(n) time using a single pass through P in the y-coordinate.
- Source overlap: `1.0`
- Kept terms: `constructed, coordinate, n, o, p, pass, single, sy, through, time, using, y`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| procedure_step | Construct Sy in O(n) time by a single pass through P in y | weak | P=False S=False | 0.9 | 1.0 | False | no procedure-like language, role symbols: n, o, p, sy, y, symbol overlap: n, o, p, sy, y |

### `4bdd952c-2df5-41c2-98bb-1287990f94b0::p00`

- Document: `closest-pair`
- Element: `4bdd952c-2df5-41c2-98bb-1287990f94b0`
- Proposition: Claim 5.2.
- Source overlap: `1.0`
- Kept terms: `5.2, claim`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Claim 5.2 | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `afb6d561-9200-4cb9-973f-1f6fe3cf962e::p00`

- Document: `closest-pair`
- Element: `afb6d561-9200-4cb9-973f-1f6fe3cf962e`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Closest Pair of Points in the Plane | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source, role symbols: but, not |

### `a46ab66d-5834-4ffe-a088-a167c7ea101a::p00`

- Document: `closest-pair`
- Element: `a46ab66d-5834-4ffe-a088-a167c7ea101a`
- Proposition: Since at most one point of S can be in any box, there are at least 3 rows of boxes separating points s and t.
- Source overlap: `1.0`
- Kept terms: `3, any, box, boxes, least, most, one, point, points, rows, s, separating, since, t`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | separation of s and t by boxes | weak | P=False S=False | 0.75 | 1.0 | False | no setup/condition-like language, role symbols: s, t, symbol overlap: s, t |

### `a46ab66d-5834-4ffe-a088-a167c7ea101a::p01`

- Document: `closest-pair`
- Element: `a46ab66d-5834-4ffe-a088-a167c7ea101a`
- Proposition: There can be at most one point of S in each box.
- Source overlap: `0.8333`
- Kept terms: `box, most, one, point, s`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| assumption | point-in-box restriction | weak | P=False S=False | 0.6667 | 0.75 | False | no setup/condition-like language, role symbols: box, one, per, s, symbol overlap: box, one, s |

### `a587dac2-50f0-4477-88a4-fad5e85415db::p00`

- Document: `closest-pair`
- Element: `a587dac2-50f0-4477-88a4-fad5e85415db`
- Proposition: As any two points in Z separated by at least 3 rows of boxes must be of distance at least 3ω/2 apart.
- Source overlap: `1.0`
- Kept terms: `2, 3, any, apart, boxes, distance, least, must, omega, points, rows, separated, two, z`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | distance between points in Z | weak | P=False S=False | 0.75 | 1.0 | False | no definition-like language, role symbols: omega, z, symbol overlap: omega, z |

### `cf237c37-1e0c-4ef1-ace2-9021261af4b3::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `cf237c37-1e0c-4ef1-ace2-9021261af4b3`
- Proposition: Human biological diversity is interrelated to changes in environmental conditions
- Source overlap: `1.0`
- Kept terms: `biological, changes, conditions, diversity, environmental, human, interrelated`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | Human biological diversity is interrelated to changes in environmental conditions | weak | P=True S=True | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition, target appears in source |

### `4a280e02-b110-4ca9-ba8a-b66565d17566::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `4a280e02-b110-4ca9-ba8a-b66565d17566`
- Proposition: One of humanity’s greatest adaptations is the development of culture
- Source overlap: `1.0`
- Kept terms: `adaptations, culture, development, greatest, humanity, one, s`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | One of humanity’s greatest adaptations is the development of culture | weak | P=True S=True | 1.0 | 1.0 | False | no setup/condition-like language, target appears in proposition, target appears in source, role symbols: one, s, symbol overlap: one, s |

### `e42b45bb-19f7-4722-9472-45e6472ed586::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `e42b45bb-19f7-4722-9472-45e6472ed586`
- Proposition: Principles of Heredity
- Source overlap: `1.0`
- Kept terms: `heredity, principles`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Principles of Heredity | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `9a25539a-60b8-4580-a398-fd8c9e5de1d9::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `9a25539a-60b8-4580-a398-fd8c9e5de1d9`
- Proposition: Penetrance is mentioned as a concept on page 3.
- Source overlap: `0.2`
- Kept terms: `penetrance`
- Novel terms: `3, concept, mentioned, page`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Penetrance | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `3a1e133f-0eca-40bf-8f6c-8e33750ca995::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `3a1e133f-0eca-40bf-8f6c-8e33750ca995`
- Proposition: Dominant versus recessive are discussed as genetic patterns on page 3.
- Source overlap: `0.25`
- Kept terms: `dominant, recessive`
- Novel terms: `3, discussed, genetic, page, patterns, versus`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Dominant vs. recessive | weak | P=False S=True | 1.0 | 0.5 | False | no definition-like language, target appears in source, role symbols: one, vs, symbol overlap: vs |

### `4de67ee1-f318-4c25-abf8-1c532779a0ad::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `4de67ee1-f318-4c25-abf8-1c532779a0ad`
- Proposition: Expression is addressed as a concept on page 3.
- Source overlap: `0.2`
- Kept terms: `expression`
- Novel terms: `3, addressed, concept, page`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Expression | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `59159ecf-a1e9-4587-bf5f-9830f42fe36f::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `59159ecf-a1e9-4587-bf5f-9830f42fe36f`
- Proposition: Phenotype and Genotype are discussed as related concepts on page 3.
- Source overlap: `0.2857`
- Kept terms: `genotype, phenotype`
- Novel terms: `3, concepts, discussed, page, related`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Phenotype | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |
| definition | Genotype | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `57a0345c-65d9-4028-8b6c-5ebc86bbfced::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `57a0345c-65d9-4028-8b6c-5ebc86bbfced`
- Proposition: The section on page 4 is titled "Heredity Punnett Square".
- Source overlap: `0.4286`
- Kept terms: `heredity, punnett, square`
- Novel terms: `4, page, section, titled`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Heredity Punnett Square | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `30434f75-28ad-4dcc-a5f6-756e79d04b7a::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `30434f75-28ad-4dcc-a5f6-756e79d04b7a`
- Proposition: Heredity is illustrated by a Punnett Square.
- Source overlap: `0.75`
- Kept terms: `heredity, punnett, square`
- Novel terms: `illustrated`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | Heredity is illustrated by a Punnett Square | weak | P=True S=False | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition |

### `30434f75-28ad-4dcc-a5f6-756e79d04b7a::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `30434f75-28ad-4dcc-a5f6-756e79d04b7a`
- Proposition: The section title indicates a focus on Punnett Squares in heredity.
- Source overlap: `0.2857`
- Kept terms: `heredity, punnett`
- Novel terms: `focus, indicates, section, squares, title`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Heredity Punnett Square | weak | P=False S=True | 1.0 | 0.0 | False | no definition-like language, target appears in source |

### `a4c211f4-8627-4138-8b44-97108796c166::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `a4c211f4-8627-4138-8b44-97108796c166`
- Proposition: About 16 genes control eye color in humans.
- Source overlap: `1.0`
- Kept terms: `16, about, color, control, eye, genes, humans`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | About 16 genes control eye color in humans | weak | P=True S=True | 1.0 | 1.0 | False | no setup/condition-like language, target appears in proposition, target appears in source, role symbols: eye, symbol overlap: eye |

### `a4c211f4-8627-4138-8b44-97108796c166::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `a4c211f4-8627-4138-8b44-97108796c166`
- Proposition: Even a dihybrid Punnett Square is too simple for eye color genetics.
- Source overlap: `0.8889`
- Kept terms: `color, dihybrid, even, eye, punnett, simple, square, too`
- Novel terms: `genetics`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | Even a dihybrid Punnett Square is too simple | weak | P=True S=True | 1.0 | 1.0 | False | no setup/condition-like language, target appears in proposition, target appears in source, role symbols: too, symbol overlap: too |

### `b55b21da-c437-4de9-ba34-ac3d6dd7cf56::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `b55b21da-c437-4de9-ba34-ac3d6dd7cf56`
- Proposition: Somatic cells are body cells.
- Source overlap: `1.0`
- Kept terms: `body, cells, somatic`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Somatic cells | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `7bf68619-af6a-44c3-851b-3fefa9004dd7::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `7bf68619-af6a-44c3-851b-3fefa9004dd7`
- Proposition: Gametes are sex cells.
- Source overlap: `1.0`
- Kept terms: `cells, gametes, sex`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Gametes | weak | P=True S=True | 1.0 | 1.0 | False | no definition-like language, target appears in proposition, target appears in source, role symbols: sex, symbol overlap: sex |

### `f48ce66f-1c15-441e-97d1-48adf13c9acf::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `f48ce66f-1c15-441e-97d1-48adf13c9acf`
- Proposition: Chromosomes
- Source overlap: `1.0`
- Kept terms: `chromosomes`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Chromosomes | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `e5dba726-c866-4668-8f65-620486e575c0::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `e5dba726-c866-4668-8f65-620486e575c0`
- Proposition: 46 each cell
- Source overlap: `1.0`
- Kept terms: `46, cell, each`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | 46 each cell | weak | P=True S=True | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition, target appears in source, role symbols: per |

### `e5dba726-c866-4668-8f65-620486e575c0::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `e5dba726-c866-4668-8f65-620486e575c0`
- Proposition: 23 pairs
- Source overlap: `1.0`
- Kept terms: `23, pairs`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| assumption | 23 pairs | weak | P=True S=True | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition, target appears in source |

### `5f72cd66-ec93-448d-81d9-1e4f130622b0::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `5f72cd66-ec93-448d-81d9-1e4f130622b0`
- Proposition: Mitosis and Meiosis
- Source overlap: `1.0`
- Kept terms: `meiosis, mitosis`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Mitosis and Meiosis | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `5f72cd66-ec93-448d-81d9-1e4f130622b0::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `5f72cd66-ec93-448d-81d9-1e4f130622b0`
- Proposition: Mitosis
- Source overlap: `1.0`
- Kept terms: `mitosis`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Mitosis | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `69493784-4662-497d-9af2-d474b5426e1a::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `69493784-4662-497d-9af2-d474b5426e1a`
- Proposition: Mitosis
- Source overlap: `1.0`
- Kept terms: `mitosis`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Mitosis | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `6aec6014-431b-40a6-b047-f737f84244d4::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `6aec6014-431b-40a6-b047-f737f84244d4`
- Proposition: Replication of somatic cells
- Source overlap: `1.0`
- Kept terms: `cells, replication, somatic`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Replication of somatic cells | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source, role symbols: non |

### `3d8d62f2-5c81-4713-b633-16a00107d130::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `3d8d62f2-5c81-4713-b633-16a00107d130`
- Proposition: Mitosis and Meiosis
- Source overlap: `1.0`
- Kept terms: `meiosis, mitosis`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Mitosis and Meiosis | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `8952226e-21e2-4901-b8af-c18b961a9d49::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `8952226e-21e2-4901-b8af-c18b961a9d49`
- Proposition: Meiosis is a heading on page 10.
- Source overlap: `0.25`
- Kept terms: `meiosis`
- Novel terms: `10, heading, page`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Meiosis | grounded | P=True S=True | 1.0 | 0.0 | True | definition-like language, target appears in proposition, target appears in source |

### `8952226e-21e2-4901-b8af-c18b961a9d49::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `8952226e-21e2-4901-b8af-c18b961a9d49`
- Proposition: Page 10 contains the heading "Meiosis".
- Source overlap: `0.2`
- Kept terms: `meiosis`
- Novel terms: `10, contains, heading, page`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| proof_setup | Page 10 heading | weak | P=False S=False | 1.0 | 0.0 | False | no setup/condition-like language |

### `00d5fbc3-a69b-4fff-8a95-52d3aa843566::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `00d5fbc3-a69b-4fff-8a95-52d3aa843566`
- Proposition: On page 10, there is a text about production of specialized cells from gametes.
- Source overlap: `0.5`
- Kept terms: `cells, gametes, production, specialized`
- Novel terms: `10, about, page, text`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | Production of specialized cells from gametes | weak | P=True S=True | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition, target appears in source |

### `6aebd0d4-2387-482d-ae19-d5e14f5614d9::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `6aebd0d4-2387-482d-ae19-d5e14f5614d9`
- Proposition: DNA is a topic introduced as a title on page 11.
- Source overlap: `0.1667`
- Kept terms: `dna`
- Novel terms: `11, introduced, page, title, topic`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | DNA | grounded | P=True S=True | 1.0 | 1.0 | True | definition-like language, target appears in proposition, target appears in source, role symbols: dna, symbol overlap: dna |

### `6aebd0d4-2387-482d-ae19-d5e14f5614d9::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `6aebd0d4-2387-482d-ae19-d5e14f5614d9`
- Proposition: The term DNA stands for Deoxyribonucleic Acid as a titled section on page 11.
- Source overlap: `0.3333`
- Kept terms: `acid, deoxyribonucleic, dna`
- Novel terms: `11, page, section, stands, term, titled`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Deoxyribonucleic Acid (DNA) | weak | P=False S=False | 1.0 | 1.0 | False | no definition-like language, role symbols: dna, symbol overlap: dna |

### `171e7cff-2c30-4a17-a719-b799b2c325d8::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `171e7cff-2c30-4a17-a719-b799b2c325d8`
- Proposition: There is text on page 11 about the combination of bases in a twisted double-helix.
- Source overlap: `0.5556`
- Kept terms: `bases, combination, double, helix, twisted`
- Novel terms: `11, about, page, text`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | Combination of bases in a twisted double-helix | weak | P=True S=True | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition, target appears in source, role symbols: dna |

### `cbd9cd93-dcc9-4584-8921-196c646862dc::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `cbd9cd93-dcc9-4584-8921-196c646862dc`
- Proposition: There is text on page 11 about the storage of genetic information.
- Source overlap: `0.4286`
- Kept terms: `genetic, information, storage`
- Novel terms: `11, about, page, text`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | Storage of genetic information | weak | P=True S=True | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition, target appears in source, role symbols: dna |

### `4a65f845-0915-4252-81ec-eab400c76868::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `4a65f845-0915-4252-81ec-eab400c76868`
- Proposition: The TED talk referenced is Drew Berry: Animations of unseeable biology.
- Source overlap: `0.875`
- Kept terms: `animations, berry, biology, drew, talk, ted, unseeable`
- Novel terms: `referenced`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Drew Berry TED talk | weak | P=False S=False | 1.0 | 1.0 | False | no definition-like language, role symbols: ted, symbol overlap: ted |

### `7f66d897-2e03-4138-a80d-fbaef2c086ca::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `7f66d897-2e03-4138-a80d-fbaef2c086ca`
- Proposition: Sources of Variability
- Source overlap: `1.0`
- Kept terms: `sources, variability`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Sources of Variability | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `1547f59b-faa7-4edb-99b9-2453434230c3::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `1547f59b-faa7-4edb-99b9-2453434230c3`
- Proposition: Genetic recombination
- Source overlap: `1.0`
- Kept terms: `genetic, recombination`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Genetic recombination | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `1d70d51c-f614-4a41-9531-368b80cba495::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `1d70d51c-f614-4a41-9531-368b80cba495`
- Proposition: Segregation
- Source overlap: `1.0`
- Kept terms: `segregation`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Segregation | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `efb9c902-0dd4-4dc9-a1ac-1bd6b5e87292::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `efb9c902-0dd4-4dc9-a1ac-1bd6b5e87292`
- Proposition: specific sorting of chromosomes
- Source overlap: `0.6667`
- Kept terms: `chromosomes, sorting`
- Novel terms: `specific`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | specific sorting of chromosomes | weak | P=True S=False | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition |

### `5ab00ef4-69cc-4443-8f87-bcee66827eee::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `5ab00ef4-69cc-4443-8f87-bcee66827eee`
- Proposition: Crossing-over
- Source overlap: `1.0`
- Kept terms: `crossing, over`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Crossing-over | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `d22e6633-75c7-4039-8bac-72a952208b83::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `d22e6633-75c7-4039-8bac-72a952208b83`
- Proposition: Genes on separate chromosomes.
- Source overlap: `1.0`
- Kept terms: `chromosomes, genes, separate`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Genes on separate chromosomes | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `d22e6633-75c7-4039-8bac-72a952208b83::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `d22e6633-75c7-4039-8bac-72a952208b83`
- Proposition: Genes on separate chromosomes.
- Source overlap: `1.0`
- Kept terms: `chromosomes, genes, separate`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | Genes on separate chromosomes | weak | P=True S=True | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition, target appears in source |

### `f02a10e0-f943-4d7e-995f-4b5fd76b6fdf::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `f02a10e0-f943-4d7e-995f-4b5fd76b6fdf`
- Proposition: Genetics and Evolution
- Source overlap: `1.0`
- Kept terms: `evolution, genetics`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Genetics and Evolution | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `205e45ed-3edb-4777-8418-497cb5af4269::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `205e45ed-3edb-4777-8418-497cb5af4269`
- Proposition: REQUIREMENTS FOR
- Source overlap: `1.0`
- Kept terms: `requirements`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | REQUIREMENTS FOR | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `205e45ed-3edb-4777-8418-497cb5af4269::p01`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `205e45ed-3edb-4777-8418-497cb5af4269`
- Proposition: REQUIREMENTS FOR
- Source overlap: `1.0`
- Kept terms: `requirements`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | REQUIREMENTS FOR | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `dd3d0938-619e-4a9d-9342-6e7491d71659::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `dd3d0938-619e-4a9d-9342-6e7491d71659`
- Proposition: REQUIREMENTS FOR
- Source overlap: `1.0`
- Kept terms: `requirements`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | REQUIREMENTS FOR | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `32b32b4e-2fb4-4372-92d8-5194345e5416::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `32b32b4e-2fb4-4372-92d8-5194345e5416`
- Proposition: Evolutionary history
- Source overlap: `1.0`
- Kept terms: `evolutionary, history`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Evolutionary history | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `64862dbc-e277-4429-be0e-2be546ec43dd::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `64862dbc-e277-4429-be0e-2be546ec43dd`
- Proposition: A Genetic Bottleneck
- Source overlap: `1.0`
- Kept terms: `bottleneck, genetic`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | A Genetic Bottleneck | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `691d0dde-d1d7-4bc6-bd46-028a3cccb540::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `691d0dde-d1d7-4bc6-bd46-028a3cccb540`
- Proposition: Original population is composed of red genetic members.
- Source overlap: `1.0`
- Kept terms: `composed, genetic, members, original, population, red`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Original population composed of red genetic members | weak | P=False S=False | 1.0 | 1.0 | False | no definition-like language, role symbols: red, symbol overlap: red |
| claim | The population includes red genetic members | weak | P=False S=False | 0.8 | 1.0 | False | no setup/condition-like language, role symbols: red, symbol overlap: red |

### `d1f99ca9-88d8-48bc-89cf-bde86e057d8a::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `d1f99ca9-88d8-48bc-89cf-bde86e057d8a`
- Proposition: A bottleneck event occurs in which the population is greatly reduced.
- Source overlap: `0.8333`
- Kept terms: `bottleneck, event, greatly, population, reduced`
- Novel terms: `occurs`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| condition | Bottleneck event occurs | weak | P=True S=False | 1.0 | 0.0 | False | no setup/condition-like language, target appears in proposition |
| definition | Bottleneck | weak | P=True S=True | 1.0 | 0.0 | False | no definition-like language, target appears in proposition, target appears in source |

### `a944f4ee-4f14-48c4-8fc9-a9976f42cd8d::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `a944f4ee-4f14-48c4-8fc9-a9976f42cd8d`
- Proposition: Only a few red individuals survive to pass their reduced number of genes to the new red population.
- Source overlap: `1.0`
- Kept terms: `few, genes, individuals, new, number, only, pass, population, red, reduced, survive`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| procedure_step | Survival leads to gene transfer to new population | weak | P=False S=False | 0.3333 | 1.0 | False | no procedure-like language, role symbols: few, new, red, symbol overlap: few, new, red |
| definition | reduced gene pool | weak | P=False S=False | 0.3333 | 1.0 | False | no definition-like language, role symbols: new, red, symbol overlap: new, red |

### `866f347c-9899-41a5-9c47-aa5db5d20cb9::p00`

- Document: `09-Inheritance_fowler_anth1210_24`
- Element: `866f347c-9899-41a5-9c47-aa5db5d20cb9`
- Proposition: © W.P. Armstrong 2001
- Source overlap: `1.0`
- Kept terms: `2001, armstrong, p, w`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Copyright notice | weak | P=False S=False | 0.0 | 1.0 | False | no definition-like language, role symbols: p, w, symbol overlap: p, w |

## grounded

- Count: `188`

### `3233c173-587a-4510-9f21-b4acc519b4fe::p00`

- Document: `closest-pair`
- Element: `3233c173-587a-4510-9f21-b4acc519b4fe`
- Proposition: Closest Pair of Points in the Plane is the title of the document.
- Source overlap: `0.6667`
- Kept terms: `closest, pair, plane, points`
- Novel terms: `document, title`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Closest Pair of Points in the Plane | grounded | P=True S=True | 1.0 | 0.0 | True | definition-like language, target appears in proposition, target appears in source |

### `f7929612-5876-487f-89ba-77302c354688::p00`

- Document: `closest-pair`
- Element: `f7929612-5876-487f-89ba-77302c354688`
- Proposition: A set of n points P = {p1, p2, ..., pn} in the Euclidean plane is given as input.
- Source overlap: `0.4545`
- Kept terms: `given, n, plane, points, set`
- Novel terms: `euclidean, input, p, p1, p2, pn`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| assumption | P = {p1, p2, ..., pn} in the Euclidean plane | grounded | P=True S=False | 1.0 | 1.0 | True | setup/condition-like language, target appears in proposition, role symbols: p, pn, symbol overlap: p, pn |

### `6b8153d9-4f9d-477a-9c66-6f794168ec52::p00`

- Document: `closest-pair`
- Element: `6b8153d9-4f9d-477a-9c66-6f794168ec52`
- Proposition: In this problem, the input is a list of n points P = {p1, p2, ..., pn} in the Euclidean plane where pi = (xi, yi), for each i = 1 to n.
- Source overlap: `1.0`
- Kept terms: `1, each, euclidean, i, input, list, n, p, p1, p2, pi, plane, pn, points, problem, xi`
- Novel terms: ``

### `13ca234b-6c24-46d6-b6b9-e09bd9797194::p00`

- Document: `closest-pair`
- Element: `13ca234b-6c24-46d6-b6b9-e09bd9797194`
- Proposition: For any two points pi and pj in P, d(pi, pj) denotes the standard Euclidean distance between them.
- Source overlap: `0.9231`
- Kept terms: `any, between, d, distance, euclidean, p, pi, pj, points, standard, them, two`
- Novel terms: `denotes`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | d(pi, pj) | grounded | P=True S=True | 1.0 | 1.0 | True | definition-like language, target appears in proposition, target appears in source, role symbols: d, d(pi,pj), pi, pj, symbol overlap: d, d(pi,pj), pi, pj |

### `989a2922-f52e-4f60-83f9-38178b0f2a12::p00`

- Document: `closest-pair`
- Element: `989a2922-f52e-4f60-83f9-38178b0f2a12`
- Proposition: To make the presentation cleaner, assume that no two points in P have the same x-coordinate or the same y-coordinate.
- Source overlap: `1.0`
- Kept terms: `assume, cleaner, coordinate, make, no, p, points, presentation, same, two, x, y`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| assumption | no two points share x or y coordinates | grounded | P=False S=False | 0.7143 | 1.0 | True | setup/condition-like language, role symbols: no, x, y, symbol overlap: no, x, y |

### `97ce0acc-6a33-4948-8a0e-b25c0ce53b8e::p00`

- Document: `closest-pair`
- Element: `97ce0acc-6a33-4948-8a0e-b25c0ce53b8e`
- Proposition: Let’s make some reasonable assumptions regarding several basic operations.
- Source overlap: `1.0`
- Kept terms: `assumptions, basic, let, make, operations, reasonable, regarding, s, several, some`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | reasonable assumptions regarding several basic operations | grounded | P=True S=True | 1.0 | 0.0 | True | definition-like language, target appears in proposition, target appears in source, role symbols: act |

### `55c575db-a04b-4a19-8cf8-d69c0a80d1cb::p00`

- Document: `closest-pair`
- Element: `55c575db-a04b-4a19-8cf8-d69c0a80d1cb`
- Proposition: Our goal here is to present an algorithm which solves the problem in time O(n log n).
- Source overlap: `1.0`
- Kept terms: `algorithm, goal, here, log, n, o, our, present, problem, solves, time`
- Novel terms: ``

### `5561f627-73d3-4d5d-a52a-7f774ecce384::p00`

- Document: `closest-pair`
- Element: `5561f627-73d3-4d5d-a52a-7f774ecce384`
- Proposition: The plan is to apply a use divide-and-conquer similar to the technique used in the mergesort algorithm.
- Source overlap: `1.0`
- Kept terms: `algorithm, apply, conquer, divide, mergesort, plan, similar, technique, use, used`
- Novel terms: ``

### `8dd3811f-29b7-4f89-bb08-ef9530afa532::p00`

- Document: `closest-pair`
- Element: `8dd3811f-29b7-4f89-bb08-ef9530afa532`
- Proposition: ﬁnd a closest pair of points in the “left half” of P,
- Source overlap: `1.0`
- Kept terms: `closest, half, left, nd, p, pair, points`
- Novel terms: ``

### `41838264-4ad6-4d12-9a1e-a7b2b7ec6098::p00`

- Document: `closest-pair`
- Element: `41838264-4ad6-4d12-9a1e-a7b2b7ec6098`
- Proposition: ﬁnd a closest pair with one point in the the left half and the other point in the right half of P,
- Source overlap: `1.0`
- Kept terms: `closest, half, left, nd, one, other, p, pair, point, right`
- Novel terms: ``

### `bd983412-a9a1-4053-8782-9c0f2953bcbd::p00`

- Document: `closest-pair`
- Element: `bd983412-a9a1-4053-8782-9c0f2953bcbd`
- Proposition: return the pair that is the closest amongst the above three pairs
- Source overlap: `1.0`
- Kept terms: `above, amongst, closest, pair, pairs, return, three`
- Novel terms: ``

### `83ad266b-1f91-41c5-8e1e-33c9f8090936::p00`

- Document: `closest-pair`
- Element: `83ad266b-1f91-41c5-8e1e-33c9f8090936`
- Proposition: The recursive divided-and-conquer algorithm will solve the closest pair problem for a subset of points P →↑P.
- Source overlap: `1.0`
- Kept terms: `algorithm, closest, conquer, divided, p, pair, points, problem, recursive, solve, subset`
- Novel terms: ``

### `d8f17077-0b6b-46ef-8b83-9448ebe62042::p00`

- Document: `closest-pair`
- Element: `d8f17077-0b6b-46ef-8b83-9448ebe62042`
- Proposition: The input to this recursive divide-and-conquer algorithm, denoted by Recursive ↓Closest ↓Pair, will be two lists P → x and P → y, where
- Source overlap: `1.0`
- Kept terms: `algorithm, closest, conquer, denoted, divide, input, lists, p, pair, recursive, two, x, y`
- Novel terms: ``

### `1993ceff-a5f5-4336-8298-9e163879b12b::p00`

- Document: `closest-pair`
- Element: `1993ceff-a5f5-4336-8298-9e163879b12b`
- Proposition: Note that the contents of P → x and P → y are the same as P →.
- Source overlap: `1.0`
- Kept terms: `contents, note, p, same, x, y`
- Novel terms: ``

### `2447d883-4235-488e-9439-f01fe33be31d::p00`

- Document: `closest-pair`
- Element: `2447d883-4235-488e-9439-f01fe33be31d`
- Proposition: Before the initial call to Recursive ↓Closest ↓Pair, we sort the original list of points P by increasing x-coordinate to get a list Px and sort P by increasing y-coordinate to get the list Py.
- Source overlap: `1.0`
- Kept terms: `before, call, closest, coordinate, get, increasing, initial, list, original, p, pair, points, px, py, recursive, sort`
- Novel terms: ``

### `4e4e5f57-bfa5-424c-aadb-b43236b29971::p00`

- Document: `closest-pair`
- Element: `4e4e5f57-bfa5-424c-aadb-b43236b29971`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

### `1666ea78-de13-4272-baa8-f733a68ca358::p00`

- Document: `closest-pair`
- Element: `1666ea78-de13-4272-baa8-f733a68ca358`
- Proposition: Let us consider the design of the Recursive ↓Closest ↓Pair algorithm with input P → x and P → y.
- Source overlap: `1.0`
- Kept terms: `algorithm, closest, consider, design, input, let, p, pair, recursive, us, x, y`
- Novel terms: ``

### `e4e4cc5b-c753-47fb-9d8e-513c6b55ed9a::p00`

- Document: `closest-pair`
- Element: `e4e4cc5b-c753-47fb-9d8e-513c6b55ed9a`
- Proposition: The algorithm is given P →↑P in the form of P → x and P → y and must return a closest pair of points in P →.
- Source overlap: `1.0`
- Kept terms: `algorithm, closest, form, given, must, p, pair, points, return, x, y`
- Novel terms: ``

### `67a39aaf-a349-440a-b757-73df2e21cf06::p00`

- Document: `closest-pair`
- Element: `67a39aaf-a349-440a-b757-73df2e21cf06`
- Proposition: Formula: Let n = |P'| = |P' subscript x | = |P' subscript y |
- Source overlap: `1.0`
- Kept terms: `formula, let, n, p, subscript, x, y`
- Novel terms: ``

### `dff36b20-6906-417e-8c6b-a71c61b12a23::p00`

- Document: `closest-pair`
- Element: `dff36b20-6906-417e-8c6b-a71c61b12a23`
- Proposition: 2 The list Qy, consisting of the points in Q sorted by increasing y-coordinate,
- Source overlap: `1.0`
- Kept terms: `2, consisting, coordinate, increasing, list, points, q, qy, sorted, y`
- Novel terms: ``

### `3fa4cef8-09cf-4b92-83e5-6d1bdf5929ad::p00`

- Document: `closest-pair`
- Element: `3fa4cef8-09cf-4b92-83e5-6d1bdf5929ad`
- Proposition: 3 The list Rx, consisting of the points in R sorted by increasing x-coordinate, and
- Source overlap: `1.0`
- Kept terms: `3, consisting, coordinate, increasing, list, points, r, rx, sorted, x`
- Novel terms: ``

### `24e04180-52d9-4df6-9bb1-2e90a26087c3::p00`

- Document: `closest-pair`
- Element: `24e04180-52d9-4df6-9bb1-2e90a26087c3`
- Proposition: 4 The list Ry, consisting of the points in R sorted by increasing y-coordinate.
- Source overlap: `1.0`
- Kept terms: `4, consisting, coordinate, increasing, list, points, r, ry, sorted, y`
- Novel terms: ``

### `c5a1897f-6691-4ce0-8bc5-939d3a2d9918::p00`

- Document: `closest-pair`
- Element: `c5a1897f-6691-4ce0-8bc5-939d3a2d9918`
- Proposition: The reason these 4 lists are created is so that the algorithm can recursively call itself to ﬁnd the closest pair in Q, and the closest pair in R.
- Source overlap: `1.0`
- Kept terms: `4, algorithm, call, closest, created, itself, lists, nd, pair, q, r, reason, recursively, so`
- Novel terms: ``

### `1d5da4bf-6baa-4d51-8a5a-4b48f3fc42a5::p00`

- Document: `closest-pair`
- Element: `1d5da4bf-6baa-4d51-8a5a-4b48f3fc42a5`
- Proposition: To compute the closest pair of points in Q, recursively call Recursive ↓Closest ↓Pair(Qx, Qy).
- Source overlap: `1.0`
- Kept terms: `call, closest, compute, pair, points, q, qx, qy, recursive, recursively`
- Novel terms: ``

### `bbe5d3e7-1cd2-4852-869a-8afa4fd64368::p00`

- Document: `closest-pair`
- Element: `bbe5d3e7-1cd2-4852-869a-8afa4fd64368`
- Proposition: Similarly, to compute the closest pair of points in R, recursively call Recursive ↓Closest ↓Pair(Rx, Ry).
- Source overlap: `1.0`
- Kept terms: `call, closest, compute, pair, points, r, recursive, recursively, rx, ry, similarly`
- Novel terms: ``

### `4de228da-f792-47d3-b580-9a0fcbfcbc21::p01`

- Document: `closest-pair`
- Element: `4de228da-f792-47d3-b580-9a0fcbfcbc21`
- Proposition: It should combine or compare this pair with the results of the two recursive calls.
- Source overlap: `0.875`
- Kept terms: `calls, combine, compare, pair, recursive, results, two`
- Novel terms: `should`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| procedure_step | combine or compare with results of two recursive calls | grounded | P=False S=False | 1.0 | 0.0 | True | procedure-like language |

### `5228c5dd-9a61-4a29-9f78-60da6331a90d::p00`

- Document: `closest-pair`
- Element: `5228c5dd-9a61-4a29-9f78-60da6331a90d`
- Proposition: Suppose q→ 0 and q→ 1 are returned as a closest pair of points in Q and r→ 0 and r→ 1 are returned as a closest pair of points in R
- Source overlap: `1.0`
- Kept terms: `0, 1, closest, pair, points, q, r, returned, suppose`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| assumption | q0/q1 form a closest pair in Q and r0/r1 form a closest pair in R | grounded | P=False S=False | 0.4444 | 1.0 | True | setup/condition-like language, role symbols: q, r, symbol overlap: q, r |

### `10df1306-44f3-4f91-8197-3837b77b863f::p00`

- Document: `closest-pair`
- Element: `10df1306-44f3-4f91-8197-3837b77b863f`
- Proposition: Let ω = min{d(q→ 0, q→ 1), d(r→ 0 , r→ 1 )}
- Source overlap: `1.0`
- Kept terms: `0, 1, d, let, min, omega, q, r`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | ω defined as minimum distance between the two candidate pairs | grounded | P=False S=False | 0.125 | 1.0 | True | definition-like language, role symbols: min, omega, symbol overlap: min, omega |

### `ce0cf796-65d5-475d-9d5c-3da8b9280c50::p00`

- Document: `closest-pair`
- Element: `ce0cf796-65d5-475d-9d5c-3da8b9280c50`
- Proposition: The algorithm needs to answer the question: Is there a pair of points q →Q, r →R such that d(q, r) < ω?
- Source overlap: `1.0`
- Kept terms: `algorithm, answer, d, needs, omega, pair, points, q, question, r, such`
- Novel terms: ``

### `cc357c07-970d-4162-b739-3ee45b4934e1::p00`

- Document: `closest-pair`
- Element: `cc357c07-970d-4162-b739-3ee45b4934e1`
- Proposition: If the answer is no, then one of the pairs q→ 0, q→ 1 or r→ 0 , r→ 1 is the closest pair in P →.
- Source overlap: `1.0`
- Kept terms: `0, 1, answer, closest, no, one, p, pair, pairs, q, r`
- Novel terms: ``

### `4b3c6a26-4ac6-4f75-8dcf-9c01c773e109::p00`

- Document: `closest-pair`
- Element: `4b3c6a26-4ac6-4f75-8dcf-9c01c773e109`
- Proposition: If the answer is yes, then a pair (p, q) where q →Q, r →R form a closest pair in P →, which the algorithm needs to compute.
- Source overlap: `1.0`
- Kept terms: `algorithm, answer, closest, compute, form, needs, p, pair, q, r, yes`
- Novel terms: ``

### `28bd0273-326c-4cf0-afee-856934de800d::p00`

- Document: `closest-pair`
- Element: `28bd0273-326c-4cf0-afee-856934de800d`
- Proposition: We now proceed to show how this question can be e!ciently answered.
- Source overlap: `1.0`
- Kept terms: `answered, ciently, e, now, proceed, question, show, we`
- Novel terms: ``

### `99b651ad-578e-4e28-b499-c049e8b5acfd::p00`

- Document: `closest-pair`
- Element: `99b651ad-578e-4e28-b499-c049e8b5acfd`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

### `311cfa1c-426b-4755-8951-8d20ee2d43c4::p00`

- Document: `closest-pair`
- Element: `311cfa1c-426b-4755-8951-8d20ee2d43c4`
- Proposition: Let x→denote the x-coordinate of the rightmost point in Q and let L denote a vertical line given by x = x→.
- Source overlap: `1.0`
- Kept terms: `coordinate, denote, given, l, let, line, point, q, rightmost, vertical, x`
- Novel terms: ``

### `026279c1-c782-484e-9cd5-45f8c8357f5f::p00`

- Document: `closest-pair`
- Element: `026279c1-c782-484e-9cd5-45f8c8357f5f`
- Proposition: This line L separates Q and R.
- Source overlap: `1.0`
- Kept terms: `l, line, q, r, separates`
- Novel terms: ``

### `50b28678-2a11-470f-8b59-1ea5258a929e::p00`

- Document: `closest-pair`
- Element: `50b28678-2a11-470f-8b59-1ea5258a929e`
- Proposition: The ﬁgure on the next slide shows the partition of L and R by the line L.
- Source overlap: `1.0`
- Kept terms: `gure, l, line, next, partition, r, shows, slide`
- Novel terms: ``

### `ece03d49-823b-4ca5-8323-794bbde00327::p00`

- Document: `closest-pair`
- Element: `ece03d49-823b-4ca5-8323-794bbde00327`
- Proposition: Claim 5.1.
- Source overlap: `1.0`
- Kept terms: `5.1, claim`
- Novel terms: ``

### `f72b8b5f-7078-4e8b-ade1-7ae2158ec759::p00`

- Document: `closest-pair`
- Element: `f72b8b5f-7078-4e8b-ade1-7ae2158ec759`
- Proposition: If there exists q →Q, r →R such that d(q, r) < ω, then each of q and r is within a distance ω of the line L.
- Source overlap: `1.0`
- Kept terms: `d, distance, each, exists, l, line, omega, q, r, such, within`
- Novel terms: ``

### `be992fa5-b77e-4cfe-a231-edf257fcacd6::p00`

- Document: `closest-pair`
- Element: `be992fa5-b77e-4cfe-a231-edf257fcacd6`
- Proposition: Note: The distance of a point and the line L is the smallest distance between the point and the line L.
- Source overlap: `1.0`
- Kept terms: `between, distance, l, line, note, point, smallest`
- Novel terms: ``

### `be992fa5-b77e-4cfe-a231-edf257fcacd6::p01`

- Document: `closest-pair`
- Element: `be992fa5-b77e-4cfe-a231-edf257fcacd6`
- Proposition: For example, if q = (qx, qy) →Q and L is the vertical line at x→, then the distance between q and L is x→↓qx, their horizontal distance.
- Source overlap: `1.0`
- Kept terms: `between, distance, example, horizontal, l, line, q, qx, qy, vertical, x`
- Novel terms: ``

### `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a::p00`

- Document: `closest-pair`
- Element: `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a`
- Proposition: Figure (figure): A diagram showing a vertical bold line dividing the image into left and right sides.
- Source overlap: `1.0`
- Kept terms: `bold, diagram, dividing, figure, image, left, line, right, showing, sides, vertical`
- Novel terms: ``

### `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a::p01`

- Document: `closest-pair`
- Element: `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a`
- Proposition: Left side features several small open circles; a small pair of connected circles with a short segment is labeled δ above it.
- Source overlap: `1.0`
- Kept terms: `above, circles, connected, delta, features, labeled, left, open, pair, segment, several, short, side, small`
- Novel terms: ``

### `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a::p02`

- Document: `closest-pair`
- Element: `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a`
- Proposition: The left region is labeled Q near the bottom.
- Source overlap: `1.0`
- Kept terms: `bottom, labeled, left, near, q, region`
- Novel terms: ``

### `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a::p03`

- Document: `closest-pair`
- Element: `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a`
- Proposition: The right side has a group of open circles, and is labeled R at the bottom.
- Source overlap: `1.0`
- Kept terms: `bottom, circles, group, labeled, open, r, right, side`
- Novel terms: ``

### `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a::p04`

- Document: `closest-pair`
- Element: `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a`
- Proposition: The vertical line has a small circle intersecting it and is annotated with the letter L along its length..
- Source overlap: `1.0`
- Kept terms: `along, annotated, circle, intersecting, l, length, letter, line, small, vertical`
- Novel terms: ``

### `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a::p05`

- Document: `closest-pair`
- Element: `bce2aeaa-0e73-49b1-a254-8f44b1a51f1a`
- Proposition: δ L Q R
- Source overlap: `1.0`
- Kept terms: `delta, l, q, r`
- Novel terms: ``

### `c827c931-911a-4e1c-8e62-0f4d502693c3::p00`

- Document: `closest-pair`
- Element: `c827c931-911a-4e1c-8e62-0f4d502693c3`
- Proposition: Figure: The partition of P →into Q and R and the line L separating the two sets of points
- Source overlap: `1.0`
- Kept terms: `figure, l, line, p, partition, points, q, r, separating, sets, two`
- Novel terms: ``

### `85cb20e5-23ca-42d2-8890-dd6ad60290ff::p00`

- Document: `closest-pair`
- Element: `85cb20e5-23ca-42d2-8890-dd6ad60290ff`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

### `89ee9ad9-1377-47cf-9285-be845739a0b6::p00`

- Document: `closest-pair`
- Element: `89ee9ad9-1377-47cf-9285-be845739a0b6`
- Proposition: Assume q = (qx, qy) →Q exists such d(q, r) < ω.
- Source overlap: `0.8889`
- Kept terms: `d, exists, omega, q, qx, qy, r, such`
- Novel terms: `assume`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| assumption | q = (qx, qy) →Q exists such d(q, r) < ω | grounded | P=True S=False | 1.0 | 1.0 | True | setup/condition-like language, target appears in proposition, role symbols: d, d(q,r), omega, q, qx, qy, symbol overlap: d, d(q,r), omega, q, qx, qy |

### `76b0a53b-2b4c-4324-a2fb-d38d07ba0f74::p00`

- Document: `closest-pair`
- Element: `76b0a53b-2b4c-4324-a2fb-d38d07ba0f74`
- Proposition: By deﬁnition of x→, qx ⇐x→< rx which implies
- Source overlap: `1.0`
- Kept terms: `de, implies, nition, qx, rx, x`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| proof_reason | deﬁnition of x→ | grounded | P=True S=True | 1.0 | 1.0 | True | reasoning/derivation-like language, target appears in proposition, target appears in source, role symbols: qx, rx, x, symbol overlap: qx, rx, x |

### `003a78e8-1b80-4018-9dd2-830d7af8b76b::p00`

- Document: `closest-pair`
- Element: `003a78e8-1b80-4018-9dd2-830d7af8b76b`
- Proposition: Formula: x to the power of * - q subscript x le r subscript x - q subscript x le d(q,r) < delta
- Source overlap: `1.0`
- Kept terms: `d, delta, formula, le, power, q, r, subscript, x`
- Novel terms: ``

### `acbf7911-433e-4343-a331-de4ce4924996::p00`

- Document: `closest-pair`
- Element: `acbf7911-433e-4343-a331-de4ce4924996`
- Proposition: Formula: r subscript x - x to the power of * le r subscript x - q subscript x le d(q, r) < delta.
- Source overlap: `1.0`
- Kept terms: `d, delta, formula, le, power, q, r, subscript, x`
- Novel terms: ``

### `aac3ac34-e18f-4506-a2d5-518139c6c805::p00`

- Document: `closest-pair`
- Element: `aac3ac34-e18f-4506-a2d5-518139c6c805`
- Proposition: Therefore by q and r lies within a distance ω of the line L.
- Source overlap: `1.0`
- Kept terms: `distance, l, lies, line, omega, q, r, therefore, within`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| proof_conclusion | q and r lies within a distance ω of the line L | grounded | P=True S=True | 1.0 | 1.0 | True | conclusion-like language, target appears in proposition, target appears in source, role symbols: l, omega, q, r, symbol overlap: l, omega, q, r |

### `69bc1b99-b6ce-4894-90f5-1b60b850157d::p00`

- Document: `closest-pair`
- Element: `69bc1b99-b6ce-4894-90f5-1b60b850157d`
- Proposition: If we want to find q and r that are close, we can restrict our search to the band consisting of points in P within ω distance from the line L.
- Source overlap: `0.9444`
- Kept terms: `band, close, consisting, distance, l, line, omega, our, p, points, q, r, restrict, search, want, we`
- Novel terms: `find`

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| claim | We can restrict our search to the band consisting of points in P within ω distance from the line L when seeking close q | grounded | P=False S=False | 0.9375 | 1.0 | True | setup/condition-like language, role symbols: l, omega, p, q, r, symbol overlap: l, omega, p, q, r |

### `f5a0c62d-21db-4a8c-9eea-0b5e52736b98::p00`

- Document: `closest-pair`
- Element: `f5a0c62d-21db-4a8c-9eea-0b5e52736b98`
- Proposition: Let S be those points that are within distance ω from L.
- Source overlap: `1.0`
- Kept terms: `distance, l, let, omega, points, s, within`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | S | grounded | P=True S=True | 1.0 | 1.0 | True | definition-like language, target appears in proposition, target appears in source, role symbols: l, omega, s, symbol overlap: l, omega, s |

### `18800611-e0e8-427a-a98c-430326deb838::p00`

- Document: `closest-pair`
- Element: `18800611-e0e8-427a-a98c-430326deb838`
- Proposition: Let Sy denote the list S, sorted by increasing y-coordinate.
- Source overlap: `1.0`
- Kept terms: `coordinate, denote, increasing, let, list, s, sorted, sy, y`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| definition | Sy | grounded | P=True S=True | 1.0 | 1.0 | True | definition-like language, target appears in proposition, target appears in source, role symbols: s, sy, y, symbol overlap: s, sy, y |

### `391a500f-b958-4791-ad44-df007bf907fa::p00`

- Document: `closest-pair`
- Element: `391a500f-b958-4791-ad44-df007bf907fa`
- Proposition: If s, t →S has the property that d(s, t) < ω, then s and t are within 15 positions of each other in the sorted list Sy.
- Source overlap: `1.0`
- Kept terms: `15, d, each, list, omega, other, positions, property, s, sorted, sy, t, within`
- Novel terms: ``

### `31d61eeb-ccae-4f74-9bfb-f3be2fcd89c5::p00`

- Document: `closest-pair`
- Element: `31d61eeb-ccae-4f74-9bfb-f3be2fcd89c5`
- Proposition: Proof.
- Source overlap: `1.0`
- Kept terms: `proof`
- Novel terms: ``

### `b40d0fd8-87a1-42c4-9700-4e5466347fb3::p00`

- Document: `closest-pair`
- Element: `b40d0fd8-87a1-42c4-9700-4e5466347fb3`
- Proposition: Consider the subset Z of the plane consisting of all points within a distance ω of the line L.
- Source overlap: `1.0`
- Kept terms: `all, consider, consisting, distance, l, line, omega, plane, points, subset, within, z`
- Novel terms: ``

### `4cfb3eac-2556-446c-92f4-a019adb29fb5::p00`

- Document: `closest-pair`
- Element: `4cfb3eac-2556-446c-92f4-a019adb29fb5`
- Proposition: Partition Z into square boxes with sides of length ω/2.
- Source overlap: `1.0`
- Kept terms: `2, boxes, length, omega, partition, sides, square, z`
- Novel terms: ``

### `7bbbc554-90da-4ac2-9106-f088c97ea564::p00`

- Document: `closest-pair`
- Element: `7bbbc554-90da-4ac2-9106-f088c97ea564`
- Proposition: A row of Z consists of 4 boxes
- Source overlap: `1.0`
- Kept terms: `4, boxes, consists, row, z`
- Novel terms: ``

### `0ee6964b-75e7-47f9-b8a9-8bc4a96b5fbc::p00`

- Document: `closest-pair`
- Element: `0ee6964b-75e7-47f9-b8a9-8bc4a96b5fbc`
- Proposition: A ﬁgure illustrating this partitioning of Z is given on the next slide.
- Source overlap: `1.0`
- Kept terms: `given, gure, illustrating, next, partitioning, slide, z`
- Novel terms: ``

### `c0e48a6f-aaa4-4be5-b4b9-511932378bd2::p00`

- Document: `closest-pair`
- Element: `c0e48a6f-aaa4-4be5-b4b9-511932378bd2`
- Proposition: Figure (figure): A schematic diagram with a central vertical solid line and a surrounding grid of dotted lines forming rectangular blocks.
- Source overlap: `1.0`
- Kept terms: `blocks, central, diagram, dotted, figure, forming, grid, line, lines, rectangular, schematic, solid, surrounding, vertical`
- Novel terms: ``

### `c0e48a6f-aaa4-4be5-b4b9-511932378bd2::p01`

- Document: `closest-pair`
- Element: `c0e48a6f-aaa4-4be5-b4b9-511932378bd2`
- Proposition: Labels δ/2 appear near the top-left region and along the left edge, while δ labels appear along the bottom left and bottom right near the central axis..
- Source overlap: `1.0`
- Kept terms: `2, along, appear, axis, bottom, central, delta, edge, labels, left, near, region, right, top`
- Novel terms: ``

### `c0e48a6f-aaa4-4be5-b4b9-511932378bd2::p02`

- Document: `closest-pair`
- Element: `c0e48a6f-aaa4-4be5-b4b9-511932378bd2`
- Proposition: δ/2 δ/2 δ δ
- Source overlap: `1.0`
- Kept terms: `2, delta`
- Novel terms: ``

### `e91ed507-26fb-44b3-b0e9-3b0a6a30394d::p00`

- Document: `closest-pair`
- Element: `e91ed507-26fb-44b3-b0e9-3b0a6a30394d`
- Proposition: Figure: Partition of Z into boxes with sides of length ω/2
- Source overlap: `1.0`
- Kept terms: `2, boxes, figure, length, omega, partition, sides, z`
- Novel terms: ``

### `fd1920f2-cb70-4d7d-8816-817e32deba98::p00`

- Document: `closest-pair`
- Element: `fd1920f2-cb70-4d7d-8816-817e32deba98`
- Proposition: It’s easy to see that no two points can lie in the same box since if they were in the same box that would imply they are both in Q or both in R and we know that two points both in Q or both in R has distance at most ω.
- Source overlap: `1.0`
- Kept terms: `both, box, distance, easy, imply, know, lie, most, no, omega, points, q, r, s, same, see`
- Novel terms: ``

### `e0370681-b74f-4e5b-b7ef-6264fec6ce8f::p00`

- Document: `closest-pair`
- Element: `e0370681-b74f-4e5b-b7ef-6264fec6ce8f`
- Proposition: Therefore each box contains at most one point of S.
- Source overlap: `1.0`
- Kept terms: `box, contains, each, most, one, point, s, therefore`
- Novel terms: ``

### `058a6ac4-e869-464a-b017-9956cafdf8f9::p00`

- Document: `closest-pair`
- Element: `058a6ac4-e869-464a-b017-9956cafdf8f9`
- Proposition: Now suppose s, t →S has property d(s, t) < ω and they are at least 16 positions in Sy with s appearing before t in Sy.
- Source overlap: `1.0`
- Kept terms: `16, appearing, before, d, least, now, omega, positions, property, s, suppose, sy, t, they`
- Novel terms: ``

### `bd38fe52-7a55-451d-b49f-3662a493723d::p00`

- Document: `closest-pair`
- Element: `bd38fe52-7a55-451d-b49f-3662a493723d`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

### `97fffa61-7318-4597-a00a-77e404954848::p00`

- Document: `closest-pair`
- Element: `97fffa61-7318-4597-a00a-77e404954848`
- Proposition: Therefore d(s, t) ⇒3ω/2 > ω.
- Source overlap: `1.0`
- Kept terms: `2, 3, d, omega, s, t, therefore`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| proof_reason | consequence about d(s,t) | grounded | P=False S=False | 0.6 | 1.0 | True | reasoning/derivation-like language, role symbols: d, d(s,t), omega, s, t, symbol overlap: d, d(s,t), omega, s, t |

### `5731e158-77c8-40c1-99ab-9f7d7153cd8f::p00`

- Document: `closest-pair`
- Element: `5731e158-77c8-40c1-99ab-9f7d7153cd8f`
- Proposition: But this contradicts the assumption that d(s, t) < ω.
- Source overlap: `1.0`
- Kept terms: `assumption, but, contradicts, d, omega, s, t`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| contradiction | contradiction with assumption | grounded | P=False S=False | 0.5 | 1.0 | True | reasoning/derivation-like language, role symbols: d, d(s,t), omega, s, t, symbol overlap: d, d(s,t), omega, s, t |

### `bf979c5a-6496-475a-904f-fc152e56718d::p00`

- Document: `closest-pair`
- Element: `bf979c5a-6496-475a-904f-fc152e56718d`
- Proposition: Therefore, if s, t →S has property d(s, t) < ω then they are at most 15 positions apart in the list Sy.
- Source overlap: `1.0`
- Kept terms: `15, apart, d, list, most, omega, positions, property, s, sy, t, therefore, they`
- Novel terms: ``

| Role | Target | Status | Target/source | Token overlap | Symbol overlap | Behavior | Notes |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| contradiction | final consequence | grounded | P=False S=False | 0.0 | 1.0 | True | reasoning/derivation-like language, role symbols: d, d(s,t), omega, s, sy, t, symbol overlap: d, d(s,t), omega, s, sy, t |

### `713a1b86-d19e-4e6e-bb75-dae56d46dd8f::p00`

- Document: `closest-pair`
- Element: `713a1b86-d19e-4e6e-bb75-dae56d46dd8f`
- Proposition: This means that in order to compute the smallest distance between distinct pairs of points in S, we simply need to compute, for each s →Sy, its distance with the next 15 elements Sy.
- Source overlap: `1.0`
- Kept terms: `15, between, compute, distance, distinct, each, elements, means, need, next, order, pairs, points, s, simply, smallest`
- Novel terms: ``

### `0b7d3bb2-23a5-4a96-a4ef-bd4ba403e36f::p00`

- Document: `closest-pair`
- Element: `0b7d3bb2-23a5-4a96-a4ef-bd4ba403e36f`
- Proposition: We now state the complete algorithm for ﬁnding a pair of closest points in P.
- Source overlap: `1.0`
- Kept terms: `algorithm, closest, complete, nding, now, p, pair, points, state, we`
- Novel terms: ``

### `1ef1f3f2-f05f-46c7-82c5-4dc29924776a::p00`

- Document: `closest-pair`
- Element: `1ef1f3f2-f05f-46c7-82c5-4dc29924776a`
- Proposition: The routine Closest ↓Pair is called with the set of points P.
- Source overlap: `1.0`
- Kept terms: `called, closest, p, pair, points, routine, set`
- Novel terms: ``

### `31d210c3-6563-44db-9e76-2bf6950302a0::p00`

- Document: `closest-pair`
- Element: `31d210c3-6563-44db-9e76-2bf6950302a0`
- Proposition: This routine calls the recursive routine Recursive ↓Closest ↓Pair, which ﬁnds a closest pair of points in P.
- Source overlap: `1.0`
- Kept terms: `calls, closest, nds, p, pair, points, recursive, routine`
- Novel terms: ``

### `08ca4c99-09ae-4b81-b1fc-86befa8ecca7::p00`

- Document: `closest-pair`
- Element: `08ca4c99-09ae-4b81-b1fc-86befa8ecca7`
- Proposition: The routine Recursive ↓Closest ↓Pair is given in the
- Source overlap: `1.0`
- Kept terms: `closest, given, pair, recursive, routine`
- Novel terms: ``

### `5f81b3b3-277c-47b4-8a9e-02a6ab3a9bc0::p00`

- Document: `closest-pair`
- Element: `5f81b3b3-277c-47b4-8a9e-02a6ab3a9bc0`
- Proposition: Closest Pair of Points in the Plane
- Source overlap: `1.0`
- Kept terms: `closest, pair, plane, points`
- Novel terms: ``

### `f917994e-1267-45ce-9715-b5cdf3877c59::p00`

- Document: `closest-pair`
- Element: `f917994e-1267-45ce-9715-b5cdf3877c59`
- Proposition: The initial sorting of P to obtain Px, Py requires O(n log n) time.
- Source overlap: `1.0`
- Kept terms: `initial, log, n, o, obtain, p, px, py, requires, sorting, time`
- Novel terms: ``

_Omitted 108 additional `grounded` propositions._
