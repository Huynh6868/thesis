/*********************************************
 * OPL 12.9.0.0 Model
 * Author: ASUS
 * Creation Date: Dec 10, 2025 at 8:54:55 PM
 *********************************************/

/*** Sets ***/
{int} P = ...;        // Set of patients IDs
{int} S = ...;        // Set of surgeons IDs

// Set of surgery types 
{string} SurgeryTypes = ...; 

// Set of surgeons qualified to be Responsible Surgeon for each surgery type
{boolean} S_Main[S, SurgeryTypes] = ...;

// Set of surgeons qualified to be 1st Assistant for each surgery type
{boolean} S_A1[S, SurgeryTypes] = ...;

// Set of surgeons qualified to be 2nd Assistant (can do all types as per request)
{int} S_A2 = ...;

/*** Parameters ***/
float wh =...;       // Daily working hours

// Fixed duration for each surgery type
float DurationByType[SurgeryTypes] = ...; 

// Which patient undergoes which surgery type
string PatientType[P] = ...;

float tp[p in P] = DurationByType[PatientType[p]];

float RestingTimeByType[SurgeryTypes] = ...;

float Rsp[s in S, p in P] = RestingTimeByType[PatientType[p]];

float BigM = 10000;   

/*** Decision variables ***/
dvar boolean xsp[S,P];      // 1 if surgeon s is assigned to patient p
dvar boolean wsp[S,P];      // 1 if surgeon s is the Responsible Surgeon for p
dvar boolean ysp[S,P];      // 1 if surgeon s is the 1st Assistant for p
dvar boolean zsp[S,P];      // 1 if surgeon s is the 2nd Assistant for p

// Precedence variable: 1 if patient p2 is operated after patient p by surgeon s
dvar boolean rspp[S,P,P]; 

// Team variable: 1 if surgeon s and s2 work together on patient p
dvar boolean fssp[S,S,P]; 

dvar float+ startsp[S,P];   // Start time of surgeon s for patient p
dvar float+ Us[S];          // Unproductive time per surgeon
dvar float+ Umax;           // Minimax objective (Maximum Unproductive Time)

/*** Objective function ***/
// (1) Minimize Umax
minimize Umax;

/*** Constraints ***/
subject to {

  // (2) Each patient must be assigned exactly ONE Responsible Surgeon
  forall(p in P)
    ct2_MainSurgeon:
    sum(s in S) wsp[s,p] == 1;

  // [NEW] Each patient must be assigned exactly ONE First Assistant
  forall(p in P)
    ct2_FirstAssistant:
    sum(s in S) ysp[s,p] == 1;

  // [NEW] Each patient must be assigned exactly ONE Second Assistant
  forall(p in P)
    ct2_SecondAssistant:
    sum(s in S) zsp[s,p] == 1;

  // [NEW] Skill Constraints: 
  // Surgeon must be in the qualified set to take the role
  
  // Responsible Surgeon Qualification
  forall(t in SurgeryTypes, s in S, p in P) {
    // If surgeon s is NOT in the responsible set for patient p's surgery type, wsp must be 0
     S_Main[s,t] == wsp[s,p];
  }

  // 1st Assistant Qualification
  forall(p in P, s in S) {
    if (s not in S_Assistant1[PatientType[p]])
      ysp[s,p] == 0;
  }

  // 2nd Assistant Qualification
  forall(p in P, s in S) {
    if (s not in S_Assistant2)
      zsp[s,p] == 0;
  }

  // (3) & (4) Link roles to the assignment variable (x_sp)
  // Ensure x_sp = 1 if the surgeon takes any role (w, y, or z)
  // Implicitly ensures one surgeon cannot take multiple roles for the same patient
  // because x_sp is binary (max 1), so sum(w+y+z) cannot exceed 1.
  forall(s in S, p in P) {
    ct3_LinkRole1: xsp[s,p] <= wsp[s,p] + ysp[s,p] + zsp[s,p];
    ct4_LinkRole2: xsp[s,p] >= wsp[s,p] + ysp[s,p] + zsp[s,p];
  }

  // (5) Precedence constraint: p and p2 cannot both be before each other
  forall(s in S, p in P, p2 in P : p != p2)
    ct5_Precedence: 
    rspp[s,p,p2] + rspp[s,p2,p] <= 1;

  // (6) & (7) Sequencing constraints based on assignment
  // If surgeon s operates on both p and p2, a precedence relationship must exist
  forall(s in S, p in P, p2 in P : p != p2) {
    ct6_SeqForce: 
    xsp[s,p] + xsp[s,p2] >= 2 * (rspp[s,p,p2] + rspp[s,p2,p]);
    
    ct7_SeqLimit: 
    xsp[s,p] + xsp[s,p2] <= 1 + (rspp[s,p,p2] + rspp[s,p2,p]);
  }

  // (8) Start time constraint based on sequence
  // If p is before p2, start time of p2 must be >= start time of p + duration + rest
  forall(s in S, p in P, p2 in P : p != p2)
    ct8_StartTimeSeq:
    startsp[s,p2] >= startsp[s,p] 
                   + tp[p] + Rsp[s,p] 
                   - BigM * (1 - rspp[s,p,p2]);

  // (9) & (10) Define the team variable (f_ss'p)
  // f_ss'p = 1 if both surgeon s and s2 are assigned to patient p
  forall(s in S, s2 in S : s != s2, p in P) {
    ct9_TeamForce:
    xsp[s,p] + xsp[s2,p] >= 2 * fssp[s,s2,p];
    
    ct10_TeamLimit:
    xsp[s,p] + xsp[s2,p] <= 1 + fssp[s,s2,p];
  }

  // (11) & (12) Synchronize start times for surgeons in the same team
  // If s and s2 work together, their start times must be equal
  forall(s in S, s2 in S : s != s2, p in P) {
    ct11_SyncStart1:
    startsp[s,p] >= startsp[s2,p] - wh * (1 - fssp[s,s2,p]);
    
    ct12_SyncStart2:
    startsp[s,p] <= startsp[s2,p] + wh * (1 - fssp[s,s2,p]);
  }

  // (13) Daily working hours constraint
  // Completion time (start + duration + rest) must not exceed daily limit (wh)
  forall(s in S, p in P)
    ct13_WorkingHours:
    wh >= startsp[s,p] + xsp[s,p] * (Rsp[s,p] + tp[p]);

  // [CLEAN UP] Force start time to 0 if not assigned (for cleaner results)
  forall(s in S, p in P)
    startsp[s,p] <= BigM * xsp[s,p];

  // (14) Calculate Unproductive Time (Us) for each surgeon
  // Us = Total Hours - Total Working Time (duration + rest)
  forall(s in S)
    ct14_CalcUs:
    Us[s] == wh - sum(p in P) ( xsp[s,p] * (tp[p] + Rsp[s,p]) );

  // Constraints (15) and (16) are omitted as requested.

  // (17) Define Umax (Minimax objective)
  // Umax must be greater than or equal to the unproductive time of any surgeon
  forall(s in S)
    ct17_Minimax:
    Umax >= Us[s];

}