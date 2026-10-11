"""Logical page lookup, including ImageJ contiguous stacks with a single IFD."""
import math


def page_layout(tif, index=0):
    count = len(tif.pages)
    virtual = False
    if count == 1 and tif.is_imagej:
        metadata = tif.imagej_metadata or {}
        images = int(metadata.get("images", 1))
        first = tif.pages[0]
        if images > 1 and len(first.shape) == 2:
            series = tif.series[0]
            if series.shape[-2:] != first.shape or math.prod(series.shape) != images * math.prod(first.shape):
                raise ValueError("ImageJ image count and contiguous series shape disagree")
            count, virtual = images, True
    if type(index) is not int or not 0 <= index < count:
        raise ValueError("Page index is outside the TIFF stack")
    return tif.pages[0 if virtual else index], count, virtual
