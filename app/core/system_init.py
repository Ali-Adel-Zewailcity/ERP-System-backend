# system_init.py — No initialization required.
#
# The previous implementation seeded the `permissions` table with a static catalog
# of resource/action pairs used by the dynamic RBAC system.
#
# In the new simplified system, permissions are derived entirely from the user's
# `role` column (a fixed enum) — no database catalog is needed.