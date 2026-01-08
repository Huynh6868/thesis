/****************************************************
 * Phase 1: Surgical Team Assignment (Boolean Matrix Version)
 * Logic: Team 3 people, Fixed Duration, Skill Matrices
 ****************************************************/

/*** Sets ***/
{int} P = ...;        // Set of patients
{int} S = ...;        // Set of surgeons
{int} SurgeryTypes = ...; // Set of surgery types

/*** Parameters ***/
float wh = ...;       // Daily working hours
int NumDays = ...; 

// [NEW] Boolean Matrices for Skills (1=Qualified, 0=Not)
// Indices: [SurgeonID][SurgeryType]
int IsResponsible[S][SurgeryTypes] = ...;
int IsAssistant1[S][SurgeryTypes] = ...;

// Index: [SurgeonID] (Applies to all types)
int IsAssistant2[S] = ...; 

// Duration & Resting Time (Indexed by SurgeryType)
float DurationByType[SurgeryTypes] = ...; 
float RestingTimeByType[SurgeryTypes] = ...;

// Patient Mapping
int PatientType[P] = ...;

// Calculated Parameters
float tp[p in P] = DurationByType[PatientType[p]];
float Rsp[s in S, p in P] = RestingTimeByType[PatientType[p]];

float BigM = 10000;   

/*** Decision variables ***/
dvar boolean xsp[S,P];      // Assigned
dvar boolean wsp[S,P];      // Responsible
dvar boolean ysp[S,P];      // 1st Assistant
dvar boolean zsp[S,P];      // 2nd Assistant
dvar boolean rspp[S,P,P];   // Sequence
// No team variable needed due to direct sync

dvar float+ StartTimeOp[P]; // Operation Start Time
dvar float+ startsp[S,P];   // Surgeon Start Time
dvar float+ Us[S];          
dvar float+ Umax;           

/*** Objective ***/
minimize Umax;

/*** Constraints ***/
subject to {

  // 1. TEAM COMPOSITION (Must have 3 members)
  forall(p in P) {
    sum(s in S) wsp[s,p] == 1; 
    sum(s in S) ysp[s,p] == 1; 
    sum(s in S) zsp[s,p] == 1; 
  }
  

  // Link roles
  forall(s in S, p in P) {
    xsp[s,p] == wsp[s,p] + ysp[s,p] + zsp[s,p];
  }

  // 2. SKILL QUALIFICATION (Boolean Logic)
  forall(p in P, s in S) {
    // Only assign if IsResponsible[s][Type] == 1
    wsp[s,p] <= IsResponsible[s][PatientType[p]];
    
    // Only assign if IsAssistant1[s][Type] == 1
    ysp[s,p] <= IsAssistant1[s][PatientType[p]];
    
    // Only assign if IsAssistant2[s] == 1
    zsp[s,p] <= IsAssistant2[s];
  }

  // 3. TIME SYNCHRONIZATION
  forall(s in S, p in P) {
    startsp[s,p] >= StartTimeOp[p] - BigM * (1 - xsp[s,p]);
    startsp[s,p] <= StartTimeOp[p] + BigM * (1 - xsp[s,p]);
    startsp[s,p] <= BigM * xsp[s,p]; // Cleanup
  }

  // 4. SEQUENCING
  forall(s in S, p in P, p2 in P : p != p2)
    rspp[s,p,p2] + rspp[s,p2,p] <= 1;

  forall(s in S, p in P, p2 in P : p != p2) {
    xsp[s,p] + xsp[s,p2] >= 2 * (rspp[s,p,p2] + rspp[s,p2,p]);
    xsp[s,p] + xsp[s,p2] <= 1 + (rspp[s,p,p2] + rspp[s,p2,p]);
  }

  forall(s in S, p in P, p2 in P : p != p2)
    startsp[s,p2] >= startsp[s,p] 
                   + tp[p] + Rsp[s,p] 
                   - BigM * (1 - rspp[s,p,p2]);

  // 5. WORKING HOURS & METRICS
  forall(s in S, p in P)
    wh >= startsp[s,p] + xsp[s,p] * (Rsp[s,p] + tp[p]);

  forall(s in S)
    Us[s] == wh - sum(p in P) ( xsp[s,p] * (tp[p] + Rsp[s,p]) );

  forall(s in S)
    Umax >= Us[s];
}