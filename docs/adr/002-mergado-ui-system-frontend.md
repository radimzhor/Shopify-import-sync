# ADR-002: Mergado UI System for Frontend Components

## Status
**Accepted** - 2026-03-04

## Context
The Shopify Import & Sync is a Mergado Store extension that integrates into the Mergado ecosystem. The frontend needs to provide a professional, consistent user experience that feels native to Mergado.

Users will navigate between Mergado's main interface and our extension, so visual and UX consistency is critical for a seamless experience.

### Requirements
- Professional appearance matching Mergado platform
- Responsive design for desktop/tablet
- Accessible UI components (WCAG 2.1)
- Fast development with pre-built components
- Consistency across the Mergado ecosystem

## Decision
We will use the **Mergado UI System (MUS)** as our component library.

**Source**: https://mus.mergado.com/

### Implementation Approach
- Use MUS components for all UI elements: buttons, forms, tables, modals, cards, etc.
- Extend Jinja2 `base.html` template with MUS CSS/JS
- Follow MUS design patterns for layouts and interactions
- Use MUS color palette and typography
- Implement custom CSS only when MUS doesn't provide a component

### Technology Stack
- **Templates**: Jinja2 (server-rendered)
- **Component Library**: Mergado UI System (MUS)
- **Base Framework**: Bootstrap 5 (MUS is built on top of it)
- **JavaScript**: Vanilla JS for interactions + Server-Sent Events for progress
- **Icons**: Font Awesome 6 (already included in base template)

## Alternatives Considered

### 1. Custom CSS Framework
**Approach**: Build our own design system from scratch.

**Pros**:
- Full control over design
- Can tailor exactly to our needs
- No external dependencies

**Cons**:
- Massive development time
- Would look different from Mergado platform
- Inconsistent UX for users
- Would need to maintain design system
- **Rejected**: Reinventing the wheel

### 2. Material UI / Tailwind CSS
**Approach**: Use a popular general-purpose UI framework.

**Pros**:
- Well-documented
- Large community
- Rich component library

**Cons**:
- Doesn't match Mergado's design language
- Users would see visual inconsistency
- Extra work to make it "look like Mergado"
- **Rejected**: Wrong aesthetic fit

### 3. React/Vue SPA with Separate Frontend
**Approach**: Build a single-page application with modern JS framework.

**Pros**:
- Rich interactivity
- Better separation of concerns
- Modern development experience

**Cons**:
- Adds build complexity (webpack, babel, etc.)
- Increases initial load time
- MUS components are designed for server-rendered apps
- Overkill for our use case (mostly forms and tables)
- **Rejected**: Too complex for our needs

### 4. Vanilla Bootstrap 5
**Approach**: Use raw Bootstrap without MUS layer.

**Pros**:
- Simple and well-documented
- Good mobile responsiveness

**Cons**:
- Generic look, not Mergado-specific
- Would need custom CSS to match Mergado
- Missing Mergado-specific patterns
- **Rejected**: MUS provides better Mergado integration

## Consequences

### Positive
- **Consistent UX**: Matches Mergado platform perfectly
- **Faster Development**: Pre-built components save time
- **Professional Appearance**: High-quality, tested components
- **Accessibility**: MUS components follow accessibility standards
- **Official Support**: Maintained by Mergado team
- **Documentation**: Storybook with examples at mus.mergado.com

### Negative
- **Limited Customization**: Must work within MUS constraints
- **Learning Curve**: Team needs to learn MUS patterns
- **Dependency**: Relies on Mergado maintaining MUS
- **Version Lock-in**: Updates to MUS may require code changes

### Mitigations
- **Custom Components**: For unique needs, build on top of MUS primitives
- **Documentation**: Reference MUS Storybook during development
- **Testing**: Test on different screen sizes to ensure responsiveness
- **Fallback**: If MUS component is buggy, use Bootstrap directly

## Implementation Guidelines

### Component Usage
```html
<!-- MUS Button -->
<button class="mus-btn mus-btn-primary">
    Import Products
</button>

<!-- MUS Card -->
<div class="mus-card">
    <div class="mus-card-header">Import Status</div>
    <div class="mus-card-body">
        <p>Imported 50/100 products</p>
    </div>
</div>

<!-- MUS Table -->
<table class="mus-table">
    <thead>
        <tr>
            <th>SKU</th>
            <th>Status</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>SKU123</td>
            <td><span class="mus-badge mus-badge-success">Success</span></td>
        </tr>
    </tbody>
</table>
```

### Page Structure
```html
{% extends "base.html" %}

{% block content %}
<div class="mus-container">
    <div class="mus-page-header">
        <h1>Product Import</h1>
    </div>
    
    <div class="mus-row">
        <div class="mus-col-12">
            <!-- MUS components here -->
        </div>
    </div>
</div>
{% endblock %}
```

### Progress Indicators
- Use MUS progress bars for import/sync progress
- Update via Server-Sent Events (SSE) for real-time feedback
- Show MUS spinners during loading states

### Forms
- Use MUS form controls for all inputs
- Follow MUS validation patterns
- Provide clear error messages with MUS alert components

## References
- [Mergado UI System](https://mus.mergado.com/)
- [Bootstrap 5 Documentation](https://getbootstrap.com/docs/5.0/) (MUS foundation)
- User requirement: "frontend should be constructed from the mergado official components"

## Notes
The existing `base.html` template already includes Bootstrap 5 and Font Awesome. We'll enhance it with MUS-specific classes and patterns.

If MUS documentation is incomplete, we can inspect how MUS components are used in the main Mergado application for reference.
