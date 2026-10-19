"""Auto-generated tool: test_math"""

def run(**kwargs):
    """Auto-generated handler for test_math.
    Parameters: {
    "a": {
        "type": "number",
        "required": true
    },
    "b": {
        "type": "number",
        "required": true
    }
}
    """
    a = float(kwargs.get('a', 0))
    b = float(kwargs.get('b', 0))
    return str(a + b)
