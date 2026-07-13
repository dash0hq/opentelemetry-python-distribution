# Coding Conventions

## Imports

Always use `from x import y`, never `import x`:

```python
# correct
from struct import pack
from logging import getLogger
from collections.abc import Sequence

# wrong
import struct
import logging
import collections
```

The only exception is when the module itself must be the reference — for example, when two names from different modules would collide and aliasing would obscure meaning. That situation is rare; prefer renaming the local variable instead.

## Commit cadence

Make a separate git commit after every discrete change. Do not batch unrelated
changes into a single commit. Each commit should be self-contained and leave
the repository in a working state.
