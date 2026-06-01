def object_to_cropped_str(obj, max_size=384):
    if isinstance(obj, (list, set)):
        if len(obj) > max_size:
            return "[...]"
        else:
            return [object_to_cropped_str(v, max_size=max_size) for v in obj]
    elif isinstance(obj, tuple):
        if len(obj) > max_size:
            return "(...)"
        else:
            return tuple([object_to_cropped_str(v, max_size=max_size) for v in obj])
    elif isinstance(obj, dict):
        if len(obj) > max_size:
            return "{...}"
        else:
            return {
                k: object_to_cropped_str(v, max_size=max_size) for k, v in obj.items()
            }
    elif isinstance(obj, str):
        if len(obj) > max_size:
            return "..."
        else:
            return obj

    elif isinstance(obj, bytes):
        if len(obj) > max_size:
            return "b..."
        else:
            return obj
    else:
        return obj
