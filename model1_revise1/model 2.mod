/*********************************************
 * Phase 2: Weekly Operating Room Scheduling
 * Updated to match data format (DurationByType)
 *********************************************/

/*** Sets ***/
{int} P = ...;      // Set of patients
{int} S = ...;      // Set of surgeons
{int} D = ...;      // Set of days 
{int} K = ...;      // Set of operating rooms

/*** Parameters from Data File ***/
{int} SurgeryTypes = ...;

// Read duration by type (e.g., [60, 65...])
float DurationByType[SurgeryTypes] = ...;

// Read preparation time by type (e.g., [10, 10...])
// Note: In your .dat file, you named it "PrepType"
float PrepType[SurgeryTypes] = ...;

// Mapping Patient -> Type
int PatientType[P] = ...;

// Maximum daily operating time
float bigM = 10000; 
float wh = ...; 
// --- CALCULATED PARAMETERS ---
// Automatically map Duration and Prep to each Patient p
float t[p in P] = DurationByType[PatientType[p]];
float Prep[p in P] = PrepType[PatientType[p]];

// --- INPUTS FROM PHASE 1 (VIA INCLUDE) ---
// Assignment results from Phase 1 (Surgeon - Patient - Day)
int xsp_in[S][P][D] = ...;

// Start times from Phase 1 (Surgeon - Patient - Day)
float startsp_in[S][P][D] = ...;

// number of surgeons assigned to patient p across the week
int Nassigned[p in P] = sum(s in S, d in D) xsp_in[s][p][d];

// day of surgery: find the unique day with any assignment
int DayOf[p in P] = (Nassigned[p] == 0) ? 0 :sum(d in D) ( (sum(s in S) xsp_in[s][p][d] > 0) ? d : 0 );

// fixed start time (minutes within that day): average over assigned surgeons
float FixedStart[p in P] = (Nassigned[p] == 0) ? 0 :
  sum(s in S, d in D) (xsp_in[s][p][d] * startsp_in[s][p][d]) / Nassigned[p];


/*** Decision Variables ***/
dvar boolean v[P][K];
dvar boolean s_ord[P][P][K];
dvar float+ starting[P][K];
dvar float+ completion[P][K];
dvar float+ Cmax[D];

/*** Objective ***/
minimize sum(d in D) Cmax[d];

/*** Constraints ***/
subject to {

  // 1. Room Assignment
  forall(p in P : DayOf[p] > 0) sum(k in K) v[p][k] == 1;

  // Cleanup for unscheduled patients
  forall(p in P : DayOf[p] == 0, k in K) {
    v[p][k] == 0;
    starting[p][k] == 0;
    completion[p][k] == 0;
  }

  // 2. Sequencing constraints (Same Day Only)
  forall(d in D, k in K, p in P, p2 in P : p != p2 && DayOf[p] == d && DayOf[p2] == d) {
    s_ord[p][p2][k] + s_ord[p2][p][k] <= 1;

    v[p][k] + v[p2][k] >= 2 * (s_ord[p][p2][k] + s_ord[p2][p][k]);
    v[p][k] + v[p2][k] <= 1 + (s_ord[p][p2][k] + s_ord[p2][p][k]);

    // Forward sequencing
    starting[p2][k] >= starting[p][k] 
                     + s_ord[p][p2][k] * (t[p] + Prep[p]) 
                     - U * (1 - s_ord[p][p2][k]);

    // Backward / Interleaving constraint
    starting[p][k] >= completion[p2][k] 
                    + s_ord[p2][p][k] * Prep[p2] 
                    - U * (1 - s_ord[p2][p][k]);
  }
  
  // Ensure s_ord = 0 if different days
  forall(k in K, p in P, p2 in P : DayOf[p] != DayOf[p2]) {
     s_ord[p][p2][k] == 0;
  }

  // 3. SYNCHRONIZATION WITH PHASE 1
  forall(p in P : DayOf[p] > 0, k in K)
  starting[p][k] == FixedStart[p] * v[p][k];


  // 4. Calculate Completion Time
  forall(p in P : DayOf[p] > 0, k in K)
    completion[p][k] >= starting[p][k] + v[p][k] * t[p] - U * (1 - v[p][k]);

  // 5. Calculate Cmax for each day
  forall(d in D, p in P : DayOf[p] == d, k in K)
    Cmax[d] >= completion[p][k] + v[p][k] * Prep[p];

  // Max hours limit
  forall(d in D) Cmax[d] <= U;
}

execute {
  writeln("Weekly Schedule Optimization Completed.");
  writeln("Day | Room | Patient | Start | End   | Duration | Prep");
  
  for(var d in D) {
     writeln("--- Day " + d + " --- (Makespan: " + Cmax[d] + ")");
     for(var k in K) {
        for(var p in P) {
           if(v[p][k] == 1 && DayOf[p] == d) {
              writeln(" " + d + "  |  " + k + "   |    " + p + "    |  " + starting[p][k] + "  | " + completion[p][k] + " | " + t[p] + " | " + Prep[p]);
           }
        }
     }
  }
}