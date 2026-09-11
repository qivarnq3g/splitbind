Perform a dedicated Motion Art Direction Pass on the current SplitBind frontend.

Do not redesign the application from scratch again.

Do not change backend behavior, API contracts, routing, authentication, business logic, validation, or working application flows.

The current visual redesign should be treated as the foundation.

The objective of this pass is specifically to raise the motion and interaction quality from a polished product interface to a memorable creative frontend experience.

Use Hallmark for visual discipline and art direction.

Use the official GSAP skills for motion architecture and implementation.

## Core motion concept

Create one coherent signature motion language based on the SplitBind cryptographic pipeline:

Document
→ Hash
→ DWT / DCT
→ Signature / Verification
→ Evidence
→ Cryptographic Seal

This pipeline should become the recurring visual and spatial motif of the application.

The animations across different pages should feel related, rather than like independent effects added to individual components.

Do not animate everything.

Concentrate effort into a small number of high-quality signature sequences.

## Signature sequence 1 - Application identity

Develop a reusable SplitBind cryptographic motion motif.

Possible visual elements:

* geometric lattice
* cryptographic nodes
* signal decomposition lines
* hash fragments
* verification traces
* document layers
* evidence coordinates
* seal geometry

The motif should evolve depending on the current stage of the workflow.

Reuse the visual language across major pages without simply duplicating the same animation.

## Signature sequence 2 - Issue Document

Create a strong visual representation of the issuance process.

The user should visually understand that a document is progressing through:

1. file intake
2. SHA-256 hashing
3. DWT/DCT processing
4. Ed25519 signing
5. issuance completion

The functional form must remain immediately usable.

The animation should live around or beside the workflow rather than obstructing inputs.

Consider:

* document representation entering a processing chamber
* progressive decomposition of the document into layers
* hash fragments appearing
* wavelet or frequency representation
* signing nodes converging
* final artifact becoming a sealed document

Use GSAP timelines.

Use ScrollTrigger only where scrolling actually contributes to storytelling.

Do not introduce scroll hijacking.

## Signature sequence 3 - Verify Document

Make verification feel visually different from issuance while preserving the same design language.

Possible sequence:

document enters
→ scanning pass
→ cryptographic layers become visible
→ expected and observed signals are compared
→ regions resolve
→ integrity result appears

Improve the existing laser scan effect into a coordinated verification sequence rather than an isolated decorative loop.

The user should be able to understand when:

* upload begins
* analysis begins
* cryptographic verification is running
* evidence is being resolved
* the final result becomes available

## Signature sequence 4 - Job lifecycle

Upgrade the current job timeline into a more spatial representation of processing.

States:

created
→ queued
→ processing
→ succeeded / failed

The active stage should meaningfully affect the visual system.

Avoid a simple animated progress bar.

Use coordinated movement, light, geometry, or information flow to communicate progression.

The animation must remain subtle enough that users can monitor long-running jobs comfortably.

## Signature sequence 5 - Result and verification seal

Make the final result the payoff of the preceding motion system.

For successful verification or issuance:

* progressively resolve the evidence
* converge the cryptographic geometry
* construct or reveal the final seal
* transition from analysis state to stable verified state

For failed verification:

* do not reuse the success animation with a different color
* create a distinct failure resolution
* clearly expose evidence and suspected regions

Avoid celebration-style animation.

The result should feel authoritative and technical.

## Page transitions

Keep route transitions restrained.

Do not rely on generic fade + translate + stagger as the primary source of motion personality.

Page-level transitions should support spatial continuity between workflow stages.

Where possible, reuse visual elements from the cryptographic pipeline to create continuity between routes.

## ScrollTrigger

Review the current ScrollTrigger usage.

Do not add ScrollTrigger merely because it is available.

Use it when the scroll position naturally represents progression or reveals deeper evidence.

Suitable places may include:

* technical evidence exploration
* integrity map
* issuance explanation
* verification evidence
* long result pages

Avoid unnecessary pinned sections in short functional forms.

Do not create scroll-jacking behavior.

## Motion quality

Use deliberate easing, timing, overlap, anticipation, and sequencing.

Avoid sequences composed only of:

* opacity 0 → 1
* translateY
* generic stagger
* pulse loops

Those techniques may still be used as supporting animation, but they must not be the primary visual identity.

Look for opportunities to use:

* masks
* clip paths
* SVG stroke animation
* shared visual geometry
* scale relationships
* transform origins
* coordinated timelines
* progressive geometry construction
* depth
* controlled blur
* state interpolation
* number or metadata transitions

Prioritize transform and opacity where performance matters.

Do not introduce expensive animation without justification.

## Accessibility

Maintain:

* prefers-reduced-motion support
* keyboard usability
* focus visibility
* semantic structure
* readable information without animation

The complete application must remain understandable with motion disabled.

Reduced-motion mode must eliminate large transformations, looping motion, and scroll-linked animation while preserving state changes.

## Performance

Use GSAP context correctly.

Clean up timelines, ScrollTriggers, and event listeners.

Avoid layout thrashing.

Avoid unnecessary continuous animations.

Pause or destroy animations that are not visible or no longer mounted.

Do not introduce Three.js or WebGL in this pass unless there is a very strong reason.

Prefer DOM, SVG, CSS, and GSAP.

## Visual verification

After implementing the motion pass, inspect the actual running application visually.

Do not judge motion quality from source code.

Verify the major workflows in a real Chromium browser.

Inspect at least:

* 1920x1080
* 1280x800
* 768x1024
* 375x667

For each major signature sequence, evaluate:

* visual clarity
* timing
* smoothness
* hierarchy
* whether motion supports meaning
* whether it feels generic
* whether it becomes distracting
* responsive composition
* reduced-motion behavior

Capture screenshots at meaningful states where useful.

If tooling allows video or animation capture, use it for the major sequences.

Perform another refinement pass based on what you actually observe.

## Completion criteria

Do not claim completion simply because the application builds.

The pass is complete only when:

* there is a recognizable SplitBind motion language
* Issue has a distinctive issuance sequence
* Verify has a distinctive verification sequence
* Job progression has meaningful motion
* Result pages have a strong final-state payoff
* the effects feel related across the product
* forms remain fast and usable
* responsive layouts remain correct
* reduced-motion mode works
* browser console has no relevant runtime errors

Run:

* tests
* typecheck
* production build
* lint if a lint script exists
* git diff --check

If no lint command exists, explicitly state that instead of silently omitting it.

Finally report:

1. the signature motion system created
2. major sequences implemented
3. which files/components own each sequence
4. GSAP timelines created
5. ScrollTrigger usage
6. animations deliberately not added and why
7. reduced-motion behavior
8. responsive/browser QA performed
9. visual problems discovered during QA
10. refinements made after visual observation
11. remaining limitations
12. tests, typecheck, lint, build, and git diff verification results
