# E1-FORMAL-R1 Preflight

Generated (UTC): 2026-08-02T11:31:14.218008+00:00
Status: **BLOCKED**

## Identity
- Required commit: `53e277c53b01695330652b8e1bc8a234909d56e5`
- HEAD commit: `53e277c53b01695330652b8e1bc8a234909d56e5`
- Git clean: `False`
- Python: `3.11.8`
- Platform: `Windows-10-10.0.26200-SP0`
- Processor: `Intel64 Family 6 Model 170 Stepping 4, GenuineIntel`
- Dependency file: `requirements.txt`
- Dependency hash: `5f8d3d2de65b448ce2b62937c805933de0bc0a706875245a32fffc3b2a6a073c`
- Free disk (GB): `587.48`

## Frozen Protocol
- Protocol git_commit: `ffc062557802ec726509b8b3f4c50d8d59276b4c`
- Manifest git_commit: `ffc062557802ec726509b8b3f4c50d8d59276b4c`
- Protocol config hash: `5cbd202c0dd64f76b046d275109a200c6cad840ca2a34149d97994689c7e2f9e`
- Selected baseline: `flamf_timealign_adapted`
- Selected baseline hash: `82b4ddec09b68c794580aa748df1fcc949471331ea8e0bb0e9b1ec529bff75ea`
- Data hash: `44081beb40e019ad999dc997162e7c7be9c0eb4cf562cddfb4f570ec1f7cca03`
- Target-group payload/file: `abf2b601b42c27be4f5636e2816430659ad0fff0128c72e9cd28dd0be2381b26` / `11f5974839e18716fa53f69c44b570106a944dcd50ccfebc3ff1b4f25399c579`
- Client-mapping payload/file: `e0adcf5f40cba6093cf9764b8badd297bd0f25b3b64104cc8b2470c6699ad7ff` / `804dd0fdb9f9f8865f70e42e4fba57926314d85205642e86972b98d560b3a64c`
- Pi-target hash: `04f6aa0b485b3ea431f304368eb4cb6f72b412b274c5e0ca5cfec69eeee8d254`
- Local steps in frozen protocol: `False`
- Authorized-code runtime default local_steps: `2`

## EventTraces
- seed 26001: events=True, audit_pass=True, hash_match=True, generation_commit=`53e277c53b01695330652b8e1bc8a234909d56e5`, hash=`e212661f5262e0559100d7f852c38a199dac9046b2b8c520fc913c9834f21a50`
- seed 26002: events=True, audit_pass=True, hash_match=True, generation_commit=`53e277c53b01695330652b8e1bc8a234909d56e5`, hash=`e8286dee49c025f5c3fa5bc4b9fbc658342a608c4b7374063951b2c9e56e05cb`
- seed 26003: events=True, audit_pass=True, hash_match=True, generation_commit=`53e277c53b01695330652b8e1bc8a234909d56e5`, hash=`06b434948310df5bbd72aac048ed54fb677321d681686d18a711e6a85190ee72`
- seed 26004: events=True, audit_pass=True, hash_match=True, generation_commit=`53e277c53b01695330652b8e1bc8a234909d56e5`, hash=`76b886994aeb651a406f465591180a170f2c25537dc144bf4735c6b47d9a1ec5`
- seed 26005: events=True, audit_pass=True, hash_match=True, generation_commit=`53e277c53b01695330652b8e1bc8a234909d56e5`, hash=`9fa446409c2edbb46407e0eb1cd936696117e7c6194b4b480a49f0cfb0a84d45`

## Hard Gates
- Frozen files exist: `True`
- R4 test summary present: `True`
- R4 test all_exit_zero: `True`
- Formal runs started: `False`

## Blockers
- frozen protocol git_commit=ffc062557802ec726509b8b3f4c50d8d59276b4c != required 53e277c53b01695330652b8e1bc8a234909d56e5
- FROZEN_CONFIG_MANIFEST git_commit=ffc062557802ec726509b8b3f4c50d8d59276b4c != required 53e277c53b01695330652b8e1bc8a234909d56e5
- frozen protocol missing local_steps

## Decision

E1-FORMAL-R1 = BLOCKED. No formal 5x5x100 runs were started.
E2-E9 have NOT started.

Teacher selected stop_blocked; no formal 25-run execution started.
