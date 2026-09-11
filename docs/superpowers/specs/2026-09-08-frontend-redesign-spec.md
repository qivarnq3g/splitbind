Rebuild the entire frontend UI of this application from the ground up.

This is a full visual and interaction redesign, not an incremental restyling of the existing interface.

Use the Hallmark skill as the primary design and art-direction system.

Use the official GSAP skills for motion design and implementation, including GSAP core, timelines, ScrollTrigger, React integration, and performance guidance where appropriate.

The goal is to produce a highly polished, modern, distinctive, interactive interface with intentional motion, while preserving all existing application functionality.

Before implementing anything, inspect the entire repository and understand the application.

Identify:

* all routes and pages
* layouts
* reusable components
* navigation
* forms
* dialogs
* authentication flows
* data fetching
* state management
* loading states
* error states
* empty states
* responsive behavior
* accessibility behavior
* existing tests
* API contracts
* business logic

Separate presentation concerns from application logic.

Preserve unless there is a strong technical reason to change them:

* backend behavior
* API contracts
* application logic
* authentication
* routing behavior
* data flow
* state management
* validation rules
* existing functionality

The presentation layer may be completely replaced.

You may redesign or rewrite:

* layouts
* page structure
* component markup
* component organization
* design system
* typography
* spacing
* colors
* visual hierarchy
* navigation presentation
* cards
* buttons
* forms
* dialogs
* tables
* dashboards
* empty states
* loading presentation
* icons
* imagery
* responsive layouts
* CSS and styling architecture
* interaction design
* animation

Do not simply reskin the existing components.

Treat the existing interface primarily as a functional specification of what the application must support.

Create a coherent visual system before rebuilding individual pages.

Define:

* typography scale
* spacing scale
* layout grid
* container system
* color roles
* surface hierarchy
* borders
* radii
* shadows
* interaction states
* component hierarchy
* responsive rules
* motion language

The finished product should feel intentionally art-directed rather than assembled from generic UI components.

Avoid common AI-generated UI patterns and unnecessary visual clutter.

Use Hallmark's design principles throughout the redesign.

For motion, however, this project intentionally allows a richer motion language than Hallmark's conservative default.

Use GSAP where animation materially improves hierarchy, storytelling, navigation, spatial continuity, or interaction.

Possible techniques include:

* coordinated entrance sequences
* typography reveals
* image reveals
* masks and clip-path transitions
* layout transitions
* scroll-linked storytelling
* ScrollTrigger
* pinned sections where appropriate
* timeline-based sequences
* subtle parallax where justified
* navigation transitions
* section transitions
* hover interactions
* micro-interactions

Do not animate everything.

Prefer several memorable, orchestrated motion sequences over dozens of unrelated effects.

Motion must support the visual hierarchy rather than compete with it.

Avoid gratuitous animation.

Maintain excellent performance.

Prefer transform and opacity based animation when possible.

Avoid unnecessary layout thrashing.

Clean up GSAP contexts and ScrollTriggers correctly.

Respect prefers-reduced-motion and provide appropriate reduced-motion behavior.

The application must remain fully usable without animation.

Responsive behavior is mandatory.

Design and verify the interface for:

* large desktop
* standard desktop
* tablet
* mobile

Do not treat mobile as a scaled-down desktop layout.

Recompose layouts when necessary.

Preserve functional parity with the existing application.

Every feature available before the redesign must still work unless it is explicitly identified as obsolete.

Pay special attention to:

* forms
* validation
* navigation
* dialogs
* keyboard interaction
* loading states
* error states
* empty states
* authentication
* data updates
* destructive actions
* responsive menus

Work systematically.

First analyze the application and establish the redesign architecture.

Then implement foundational systems such as tokens, typography, application shell, shared components, and motion infrastructure.

After that, migrate the application page by page.

Do not delete the old implementation prematurely.

Replace functionality incrementally and remove obsolete presentation code only after the replacement has been verified.

Reuse application logic where appropriate rather than rewriting working logic purely for aesthetic reasons.

Refactor presentation-related architecture when it materially improves the redesign.

Maintain reasonable component boundaries.

Avoid giant page components.

Avoid excessive abstraction and premature component generalization.

Before considering the redesign complete:

* run the production build
* run linting
* run type checking
* run relevant tests
* fix warnings that indicate real issues
* check for console errors
* verify navigation
* verify important application flows
* verify responsive layouts
* verify keyboard navigation
* verify reduced-motion behavior
* verify GSAP cleanup
* identify and remove unused legacy styling and components

Do not stop after making the homepage or primary screen attractive.

The redesign applies to the entire user-facing application.

The final result should feel like one deliberately designed product, not a collection of individually redesigned pages.
