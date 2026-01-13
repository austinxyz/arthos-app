# Business Logic in Services, Not Templates

## Problem

Complex business logic implemented in Jinja2 templates caused several issues:

1. **Highlighting Logic Failure**: Attempted to find and highlight Risk Reversal strategies closest to $0 Net Cost in the template, but comparisons failed due to:
   - Floating point precision issues in Jinja2
   - Difficulty comparing strategy objects
   - Complex conditional logic that was hard to debug
   - Template code becoming unmaintainable

2. **Similar Issues**: We've encountered this pattern before where template-based logic caused problems that were difficult to diagnose and fix.

## Solution

**Move business logic to the service layer (Python), not templates (Jinja2).**

### Example: Risk Reversal Highlighting

**Before (Template Logic - Problematic)**:
```jinja2
{# Complex logic in template trying to find closest strategies #}
{% set closest_negative_cost = none %}
{% set closest_positive_cost = none %}
{% for s in strategies %}
    {% if s.cost < 0 %}
        {% if closest_negative_cost is none or s.cost > closest_negative_cost %}
            {% set closest_negative_cost = s.cost %}
        {% endif %}
    {% elif s.cost > 0 %}
        {% if closest_positive_cost is none or s.cost < closest_positive_cost %}
            {% set closest_positive_cost = s.cost %}
        {% endif %}
    {% endif %}
{% endfor %}

{# Then trying to match strategies - this failed! #}
{% for strategy in strategies %}
    {% set is_closest = false %}
    {% if strategy.cost == closest_negative_cost %}
        {% set is_closest = true %}
    {% endif %}
    {# ... more complex comparisons that didn't work ... #}
{% endfor %}
```

**After (Service Logic - Reliable)**:
```python
# In app/services/stock_service.py
# After creating all strategies for an expiration:

# Find strategies closest to $0 (one negative, one positive)
closest_negative = None
closest_positive = None
closest_negative_abs = None
closest_positive_abs = None

for strategy in strategies:
    cost = strategy['cost']
    if cost < 0:
        # Negative cost - find the one closest to $0 (smallest absolute value)
        abs_cost = abs(cost)
        if closest_negative_abs is None or abs_cost < closest_negative_abs:
            closest_negative = strategy
            closest_negative_abs = abs_cost
    elif cost > 0:
        # Positive cost - find the one closest to $0 (smallest positive)
        if closest_positive_abs is None or cost < closest_positive_abs:
            closest_positive = strategy
            closest_positive_abs = cost

# Mark the closest strategies for highlighting
for strategy in strategies:
    strategy['highlight'] = (
        strategy == closest_negative or 
        strategy == closest_positive or
        strategy['cost'] == 0
    )
```

```jinja2
{# In template - simple flag check #}
{% for strategy in strategies %}
    <tr class="{% if strategy.highlight %}table-warning{% endif %}">
        {# ... render strategy data ... #}
    </tr>
{% endfor %}
```

## Best Practices

### ✅ DO:

1. **Keep Business Logic in Services**
   - Calculations, comparisons, filtering, sorting
   - Data transformations and aggregations
   - Complex conditional logic
   - Finding "closest", "best", "worst" items

2. **Use Templates for Presentation Only**
   - Rendering data that's already prepared
   - Simple conditionals for display (e.g., `{% if field %}`)
   - Formatting for display (e.g., `{{ value|format }}`)
   - Iterating over pre-processed data

3. **Pass Pre-Computed Flags/Values**
   - Add boolean flags like `highlight`, `is_selected`, `is_active`
   - Pre-calculate formatted strings
   - Include computed values in data structures

### ❌ DON'T:

1. **Don't Put Business Logic in Templates**
   - Avoid complex calculations in Jinja2
   - Don't try to find "best" or "closest" items in templates
   - Don't do complex comparisons or filtering
   - Don't implement sorting logic in templates

2. **Don't Rely on Template Comparisons**
   - Floating point comparisons are unreliable in Jinja2
   - Object comparisons may not work as expected
   - Complex conditionals are hard to debug

## Why This Matters

### 1. **Reliability**
- Python is more reliable for complex logic
- Better handling of floating point precision
- Easier to test and debug

### 2. **Maintainability**
- Business logic in one place (service layer)
- Templates stay simple and readable
- Easier to modify logic without touching templates

### 3. **Testability**
- Service logic can be unit tested
- Template logic is harder to test
- Can verify business rules independently

### 4. **Performance**
- Calculations done once in Python
- Templates just render pre-computed values
- No repeated calculations during rendering

## Architecture Pattern

```
┌─────────────────┐
│   Controller    │  (app/main.py)
│   (FastAPI)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Service      │  (app/services/*.py)
│  Business Logic │  ← All calculations, comparisons, logic here
│  Data Prep      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Template     │  (app/templates/*.html)
│   Presentation  │  ← Only rendering, simple conditionals
│   Formatting    │
└─────────────────┘
```

## Key Learnings

1. **Separation of Concerns**: Business logic belongs in services, not templates
2. **Template Limitations**: Jinja2 is great for presentation, not complex logic
3. **Pre-Compute Everything**: Do calculations in Python, pass results to templates
4. **Use Flags**: Add boolean flags to data structures for template conditionals
5. **Testability**: Service logic is easier to test than template logic

## Related Issues

- Risk Reversal highlighting logic (this document)
- Similar template logic issues encountered previously
- Test failures related to complex template conditionals

## References

- Service layer: `app/services/stock_service.py` - `calculate_risk_reversal_strategies()`
- Template: `app/templates/stock_detail.html` - Risk Reversal table rendering
- FastAPI best practices: Keep business logic out of route handlers and templates
