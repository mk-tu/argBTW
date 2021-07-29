# Call:

python argbtw.py --log=LOGLEVEL --btw-method=METHOD --task=TASK (--cnf-file=out.cnf) -f input.apx

## NECESSARY:
--btw-method=METHOD for METHOD in {"ARG_BD_SAT", "ARG_BD_ONLY", "ARG_TW_ONLY", "SAT_ENCODING"}
--log=LOGLEVEL for LOGLEVEL in {"DEBUG_SQL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
--task=TASK for TASK in {"CE-ST", "CE-ADM"}
-f input.apx for input.apx is an AF in ASPARTIX apx format

## OPTIONAL:
--cnf-file=out.cnf **(required with --btw-method=SAT_ENCODING)**
Constructs a formula in cnf (models correspond to extensions of the AF),
saves it as out.cnf and exits (i.e. does not solve the instance)





## Methods:
### ARG_BD_SAT
Backdoor-treewidth approach:
With clingo, we find an acyclicity backdoor.
Then we compute the torso, and decompose the torso.
This torso-decomposition is used to construct a cnf (decomposition guided reduction).
The cnf is solved by DP along the lines of the computed torso decomposition.

### ARG_BD_ONLY
Backdoor-only approach:
With clingo, we find an acyclicity backdoor.
Then we compute the torso.
Instead of decomposing the torso, we put the whole instance into one bag of an empty decomposition.
This (trivial) torso-decomposition is used to construct a cnf (decomposition guided reduction).
The cnf is solved by DP along the lines of the (trivial) torso decomposition.

### ARG_TW_ONLY
Treewidth approach only
As a (dummy) backdoor, all vertices are chosen.
The torso is the original graph of the instance.
We compute a decomposition for the torso (the original graph).
This decomposition is used to construct a cnf (decomposition guided reduction).
The cnf is solved by DP along the lines of the computed decomposition.


### SAT_ENCODING
**REQUIRES** --cnf-file=out.cnf to be set
Direct SAT SAT_ENCODING
Computes a cnf without regarding backdoors, treewidth, etc.
The computed cnf is stored in out.cnf


## Tasks:
### CE-ST
Count stable extensions

### CE-ADM
Count admissible sets
