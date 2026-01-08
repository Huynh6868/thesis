/*********************************************
 * OPL 12.9.0.0 Model
 * Author: ASUS
 * Creation Date: Dec 20, 2025 at 4:54:23 PM
 *********************************************/
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
float PrepType[SurgeryTypes] = ...;

// Mapping Patient -> Type
int PatientType[P] = ...;

// Maximum daily operating time
float bigM = 10000; 
float wh = ...; 
// --- CALCULATED PARAMETERS ---
float tp[p in P] = DurationByType[PatientType[p]];
float Prep[p in P] = PrepType[PatientType[p]];

// --- INPUTS FROM PHASE 1 ---
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
dvar boolean v[P,K,D];
dvar boolean s_ord[P,P,K,D];
dvar float+ starting[P,K,D];
dvar float+ completion[P,K,D];
dvar float+ Cmax[D];

/*** Objective ***/
minimize sum(d in D) Cmax[d];

/*** Constraints ***/
subject to {

  // 1. Room Assignment
  forall(p in P : DayOf[p] > 0) sum(k in K) v[p,k,DayOf[p]] == 1;
  forall(p in P : DayOf[p] > 0, k in K, d in D : d != DayOf[p]) v[p,k,d] == 0;
  // Cleanup for unscheduled patients
  forall(p in P : DayOf[p] == 0, k in K, d in D) {
    v[p,k,d] == 0;
    starting[p,k,d] == 0;
    completion[p,k,d] == 0;
  }

  // 2. Sequencing constraints (Same Day Only)
  forall(d in D, k in K, p in P, p2 in P : p != p2 && DayOf[p] == d && DayOf[p2] == d) {
    s_ord[p,p2,k,d] + s_ord[p2,p,k,d] <= 1;

    v[p,k,d] + v[p2,k,d] >= 2 *( s_ord[p,p2,k,d] + s_ord[p2,p,k,d] );
    v[p,k,d] + v[p2,k,d] <= 1 +( s_ord[p,p2,k,d] + s_ord[p2,p,k,d] );


    // Forward sequencing
    starting[p2,k,d] >= starting[p,k,d] + s_ord[p,p2,k,d] * (tp[p] + Prep[p])  - bigM * (1 - s_ord[p,p2,k,d]);

    // Backward / Interleaving constraint
    starting[p,k,d] >= completion[p2,k,d]  + s_ord[p2,p,k,d] * Prep[p2] 
                    - bigM * (1 - s_ord[p2,p,k,d]);
  }
  
  // Ensure s_ord = 0 if different days
  forall(d in D, k in K, p in P, p2 in P : DayOf[p] != DayOf[p2]) {
     s_ord[p,p2,k,d] == 0;
  }

  // 3. SYNCHRONIZATION WITH PHASE 1
  forall(p in P : DayOf[p] > 0, k in K, d in D)
  starting[p,k,d] == FixedStart[p] * v[p,k,d];


  // 4. Calculate Completion Time
  forall(p in P : DayOf[p] > 0, k in K, d in D)
    completion[p,k,d] >= starting[p,k,d] + v[p,k,d] * tp[p] - bigM * (1 - v[p,k,d]);

  // 5. Calculate Cmax for each day
  forall(d in D, p in P : DayOf[p] == d, k in K)
    Cmax[d] >= completion[p,k,d] + v[p,k,d] * Prep[p];

  // Max hours limit
  forall(d in D) Cmax[d] <= wh;
}

execute {
  var o = new IloOplOutputFile("phase2_results.dat");
  
  var numP = P.size;
  var numK = K.size;
  var numD = D.size;
  
  // Export v (room assignment): v[p][k][d]
  o.writeln("v_in = [");
  var pCount = 0;
  for(var p in P) {
     o.write("  [");
     var kCount = 0;
     for(var k in K) {
        o.write("[");
        var dCount = 0;
        for(var d in D) {
           if (v[p][k][d] >= 0.99) o.write("1"); else o.write("0");
           dCount++;
           if (dCount < numD) o.write(", ");
        }
        o.write("]");
        kCount++;
        if (kCount < numK) o.write(", ");
     }
     o.write("  ]");
     pCount++;
     if (pCount < numP) o.writeln(","); else o.writeln("");
  }
  o.writeln("];");
  
  o.close();
  writeln(">>> Exported phase2_results.dat successfully <<<");
  
  // Also print summary to console
  writeln("Weekly Schedule Optimization Completed.");
  writeln("Day | Room | Patient | Start | End   | Duration | Prep");
  
  for(var d in D) {
     writeln("--- Day " + d + " --- (Makespan: " + Cmax[d] + ")");
     for(var k in K) {
        for(var p in P) {
           if(v[p][k][d] >= 0.99 && DayOf[p] == d) {
              writeln(" " + d + "  |  " + k + "   |    " + p + "    |  " + starting[p][k][d] + "  | " + completion[p][k][d] + " | " + tp[p] + " | " + Prep[p]);
           }
        }
     }
  }
}