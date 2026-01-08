/*********************************************
 * Phase 1: Weekly Surgical Team Assignment
 * - Weekly schedule (set of days D)
 * - Each patient operated exactly once in the week
 * - Each team = 1 main + 1 first assistant + 1 second assistant
 *********************************************/

/*** Sets ***/
{int} P = ...;      // Set of patients
{int} S = ...;      // Set of surgeons
{int} D = ...;      // Set of days in the week (e.g., {1,2,3,4,5})

// Surgery types 
{int} SurgeryTypes = ...;

// Operating rooms 
{int} K = ...;

/*** Parameters ***/

// 1 if surgeon s is qualified as responsible for surgery type t on day d
int IsResponsible[S][SurgeryTypes][D] = ...;

// 1 if surgeon s is qualified as first assistant for surgery type t on day d
int IsAssistant1[S][SurgeryTypes][D] = ...;

// 1 if surgeon s is qualified as second assistant on day d (all types)
int IsAssistant2[S][D] = ...;

// Duration of each surgery type
float DurationByType[SurgeryTypes] = ...;

// OR cleaning time by type (minutes)
float PrepType[SurgeryTypes] = ...;

// For each patient p: which surgery type it belongs to
int PatientType[P] = ...;

// Duration of each patient p
float tp[p in P] = DurationByType[PatientType[p]];

// OR prep/turnover time per patient
float Prep[p in P] = PrepType[PatientType[p]];

// OR occupied time per patient (surgery + turnover)
float DurOR[p in P] = tp[p] + Prep[p];

// Daily working hours for each day d (e.g., 480 minutes)
float wh[D] = ...;
int Avail[S][D] = ...;     // 1 if surgeon s works on day d, else 0
float whSD[s in S, d in D] = wh[d] * Avail[s][d];

// Resting time by surgery type
float RestingTimeByType[SurgeryTypes] = ...;

// Rest time for surgeon s after operating patient p (depends on type only)
float Rsp[s in S, p in P] = RestingTimeByType[PatientType[p]];

// Big-M constant
float BigM = 10000;

/*** Decision variables ***/

// xsp[s,p,d] = 1 if surgeon s participates in operation p on day d (any role)
dvar boolean xsp[S,P,D];

// wsp[s,p,d] = 1 if surgeon s is the main (responsible) surgeon for p on day d
dvar boolean wsp[S,P,D];

// ysp[s,p,d] = 1 if surgeon s is first assistant for p on day d
dvar boolean ysp[S,P,D];

// zsp[s,p,d] = 1 if surgeon s is second assistant for p on day d
dvar boolean zsp[S,P,D];

// rspp[s,p,p2,d] = 1 if, for surgeon s on day d, operation p2 is after p
dvar boolean rspp[S,P,P,D];

// fssp[s,s2,p,d] = 1 if surgeons s and s2 work together on patient p on day d
dvar boolean fssp[S,S,P,D];

// Start time of surgeon s for patient p on day d
dvar float+ startsp[S,P,D];

// ------------------------------
// Operating Room capacity variables
// ------------------------------

// v[p,k,d] = 1 if patient p uses operating room k on day d
dvar boolean v[P,K,D];

// ordOR[p,p2,k,d] = 1 if (in OR k, day d) patient p is scheduled before p2
dvar boolean ordOR[P,P,K,D];

// Operation start time for patient p on day d (linked to the responsible surgeon)
dvar float+ StartOp[P,D];

// Derived expression: xpd[p,d] = 1 if patient p is scheduled on day d
dexpr int xpd[p in P, d in D] = sum(s in S) wsp[s,p,d];

// Daily unproductive time for each surgeon and day - ADDING
dvar float+ UsDay[S,D];

// Maximum unproductive time among surgeons in each day - ADDING
dvar float+ UmaxDay[D];

// Weekly unproductive time for each surgeon
dvar float+ Us[S];

// Maximum unproductive time (minimax objective)
dvar float+ Umax;

//Objective
minimize Umax;


// Constraints 
subject to {

  /***** 1. TEAM & DAY ASSIGNMENT *****/

  // (2a) Each patient has exactly ONE main surgeon in the whole week
  forall(p in P)
    sum(d in D, s in S) wsp[s,p,d] == 1;

  // (2b) At most one main surgeon for patient p on each day
  forall(p in P, d in D)
    sum(s in S) wsp[s,p,d] <= 1;

  // (2c) Each patient has exactly ONE first assistant in the whole week
  forall(p in P)
    sum(d in D, s in S) ysp[s,p,d] == 1;

  // At most one first assistant per day
  forall(p in P, d in D)
    sum(s in S) ysp[s,p,d] <= 1;

  // (2d) Each patient has exactly ONE second assistant in the whole week
  forall(p in P)
    sum(d in D, s in S) zsp[s,p,d] == 1;

  // At most one second assistant per day
  forall(p in P, d in D)
    sum(s in S) zsp[s,p,d] <= 1;

  // (2e) Main / A1 / A2 must be on the SAME day for each patient
  // On any day d, either all three roles are present (one each) or all are zero
  forall(p in P, d in D) {
    sum(s in S) wsp[s,p,d] == sum(s in S) ysp[s,p,d];
    sum(s in S) wsp[s,p,d] == sum(s in S) zsp[s,p,d];
  }

  // (3) & (4) Link roles to assignment xsp
  // One surgeon can take at most one role for patient p on day d
  forall(s in S, p in P, d in D) {
    xsp[s,p,d] <= wsp[s,p,d] + ysp[s,p,d] + zsp[s,p,d];
    xsp[s,p,d] >= wsp[s,p,d] + ysp[s,p,d] + zsp[s,p,d];
  }

  /***** 2. QUALIFICATION CONSTRAINTS *****/

  // Responsible surgeon qualification
  forall(p in P, s in S, d in D)
    wsp[s,p,d] <= IsResponsible[s][PatientType[p]][d];

  // First assistant qualification
  forall(p in P, s in S, d in D)
    ysp[s,p,d] <= IsAssistant1[s][PatientType[p]][d];

  // Second assistant qualification
  forall(p in P, s in S, d in D)
    zsp[s,p,d] <= IsAssistant2[s][d];

//CHAN ASSIGNMENT NEU NGAY DO BAC SI KHONG DI LAM
forall(s in S, p in P, d in D) {
  wsp[s,p,d] <= Avail[s][d];
  ysp[s,p,d] <= Avail[s][d];
  zsp[s,p,d] <= Avail[s][d];
  xsp[s,p,d] <= Avail[s][d];
}

  /***** 3. PRECEDENCE & SEQUENCING (WITHIN EACH DAY) *****/

  // (5) For each surgeon and each day: p and p2 cannot both precede each other
  forall(s in S, p in P, p2 in P : p != p2, d in D)
    rspp[s,p,p2,d] + rspp[s,p2,p,d] <= 1;

  // (6) & (7) If surgeon s operates on both p and p2 on day d,
  //           there must be a precedence relationship
  forall(s in S, p in P, p2 in P : p != p2, d in D) {
    xsp[s,p,d] + xsp[s,p2,d] >= 2 * (rspp[s,p,p2,d] + rspp[s,p2,p,d]);
    xsp[s,p,d] + xsp[s,p2,d] <= 1 + (rspp[s,p,p2,d] + rspp[s,p2,p,d]);
  }

  // (8) Start time constraint based on precedence
  // If p2 is after p for surgeon s on day d, start(p2) >= start(p) + duration + rest
  forall(s in S, p in P, p2 in P : p != p2, d in D)
    startsp[s,p2,d] >= startsp[s,p,d]
                      + rspp[s,p,p2,d] * (tp[p] + Rsp[s,p])
                      - BigM * (1 - rspp[s,p,p2,d]);

  /***** 4. TEAM SYNCHRONIZATION (SAME START TIME IN SAME TEAM) *****/

  // (9) & (10) Define fssp: 1 if both surgeons s and s2 attend patient p on day d
  forall(s in S, s2 in S : s != s2, p in P, d in D) {
    xsp[s,p,d]  + xsp[s2,p,d] >= 2 * fssp[s,s2,p,d];
    xsp[s,p,d]  + xsp[s2,p,d] <= 1 + fssp[s,s2,p,d];
  }

  // (11) & (12) If surgeons s and s2 are in the same team on day d,
  //             they must have the same start time
  forall(s in S, s2 in S : s != s2, p in P, d in D) {
    startsp[s,p,d] >= startsp[s2,p,d] - wh[d] * (1 - fssp[s,s2,p,d]);
    startsp[s,p,d] <= startsp[s2,p,d] + wh[d] * (1 - fssp[s,s2,p,d]);
  }

  /***** 5. DAILY WORKING HOURS & START TIME *****/

  // (13) For each surgeon, day, and patient:
  // If surgeon s operates on p on day d, completion time must be <= wh[d]
  forall(s in S, p in P, d in D)
    whSD[s][d] >= startsp[s,p,d] + xsp[s,p,d] * (Rsp[s,p] + tp[p]);

  // if surgeon s does not operate p on day d, force start time = 0
  forall(s in S, p in P, d in D)
    startsp[s,p,d] <= BigM * xsp[s,p,d];


  /***** 5b. OPERATING ROOM CAPACITY (K rooms) *****/

  // Link StartOp[p,d] to the responsible surgeon's start time
  // - If patient p is not scheduled on day d -> xpd[p,d]=0 -> StartOp[p,d]=0
  // - If scheduled -> StartOp equals the start time of the unique main surgeon
  forall(p in P, d in D) {
    StartOp[p,d] <= BigM * xpd[p,d];
    StartOp[p,d] <= wh[d];
    // If p is scheduled on day d, it must finish (incl. turnover) within the day horizon
    StartOp[p,d] + DurOR[p] <= wh[d] + BigM * (1 - xpd[p,d]);
  }

  forall(p in P, d in D, s in S) {
    StartOp[p,d] >= startsp[s,p,d] - BigM * (1 - wsp[s,p,d]);
    StartOp[p,d] <= startsp[s,p,d] + BigM * (1 - wsp[s,p,d]);
  }

  // Each scheduled surgery uses exactly one OR that day
  forall(p in P, d in D)
    sum(k in K) v[p,k,d] == xpd[p,d];

  // Non-overlap inside each OR (disjunctive sequencing)
  forall(d in D, k in K, p in P, p2 in P : p != p2) {

    // Activate ordering only when both surgeries are assigned to the same OR
    v[p,k,d] + v[p2,k,d] >= 2 * (ordOR[p,p2,k,d] + ordOR[p2,p,k,d]);
    v[p,k,d] + v[p2,k,d] <= 1 + (ordOR[p,p2,k,d] + ordOR[p2,p,k,d]);
    ordOR[p,p2,k,d] + ordOR[p2,p,k,d] <= 1;

    // If p is before p2 in OR k on day d, enforce no overlap (incl. turnover)
    StartOp[p2,d] >= StartOp[p,d] + DurOR[p] - BigM * (1 - ordOR[p,p2,k,d]);
  }



/***** 7. Daily and weekly unproductive time *****/

// Daily unproductive time:
// UsDay[s,d] = available hours in day d - total working + rest in day d
forall(s in S, d in D)
  UsDay[s][d] == whSD[s,d] - sum(p in P) xsp[s,p,d] * (tp[p] + Rsp[s,p]);

  /***** 6. WEEKLY UNPRODUCTIVE TIME & MINIMAX OBJECTIVE *****/

  // (14) Weekly unproductive time for each surgeon:
  // Total weekly capacity - total operating+rest time over all days and patients
  //forall(s in S)
   // Us[s] == sum(d in D) wh[d] - sum(d in D, p in P) xsp[s,p,d] * (tp[p] + Rsp[s,p]);
// Weekly unproductive time per surgeon:
// sum of daily idle times over all days
  forall(s in S)
    Us[s] == sum(d in D) UsDay[s,d];

// UmaxDay[d] is the maximum unproductive time among surgeons in day d
  forall(d in D, s in S)
   UmaxDay[d] >= UsDay[s,d];
  
  // (17) Umax is the maximum unproductive time among all surgeons
  forall(s in S)
    Umax >= Us[s];
}

execute {
  // Export Gantt data to CSV (day-based time axis)
  // File will be created in the project/run folder (relative path)

  var out = new IloOplOutputFile("gantt1.csv");
  out.writeln("day,surgeon,patient,start,finish,duration");

  for (var d in D)
    for (var s in S)
      for (var p in P)
        if (xsp[s][p][d] > 0.5) {                 // IMPORTANT: use [][]
          var st = startsp[s][p][d];
          var fn = st + tp[p];
          out.writeln(d + "," + s + "," + p + "," + st + "," + fn + "," + tp[p]);
        }

  out.close();
  writeln("Exported gantt1.csv successfully.");
}

execute {
   var o = new IloOplOutputFile("phase1OR_results.dat");
   
  
   var numS = S.size;
   var numP = P.size;
   var numD = D.size;


   o.writeln("xsp_in = [");
   var sCount = 0;
   for(var s in S) {
      o.write("  [");
      var pCount = 0;
      for(var p in P) {
         o.write("[");
         var dCount = 0;
         for(var d in D) {
           
            if (xsp[s][p][d] >= 0.99) o.write("1"); else o.write("0");
            
            
            dCount++;
            if (dCount < numD) o.write(", ");
         }
         o.write("]");
        
         pCount++;
         if (pCount < numP) o.write(", ");
      }
      o.write("  ]");
    
      sCount++;
      if (sCount < numS) o.writeln(","); else o.writeln("");
   }
   o.writeln("];");

   o.writeln(""); 

  
   o.writeln("startsp_in = [");
   sCount = 0;
   for(var s in S) {
      o.write("  [");
      var pCount = 0;
      for(var p in P) {
         o.write("[");
         var dCount = 0;
         for(var d in D) {
          
            o.write(Math.round(startsp[s][p][d] * 100) / 100);
            
            dCount++;
            if (dCount < numD) o.write(", ");
         }
         o.write("]");
         pCount++;
         if (pCount < numP) o.write(", ");
      }
      o.write("  ]");
      sCount++;
      if (sCount < numS) o.writeln(","); else o.writeln("");
   }
   o.writeln("];");

   o.close();
   writeln(">>> Exported phase1OR_results.dat successfully (Dynamic Size) <<<");
}