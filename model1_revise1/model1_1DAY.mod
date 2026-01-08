/*********************************************
 * OPL 12.9.0.0 Model
 * Author: ASUS
 * Creation Date: Dec 11, 2025 at 2:55:29 PM
 *********************************************/
/****************************************************
 * Phase 1: Surgical Team Assignment Problem
 ****************************************************/

//Sets 
{int} P = ...;   //Set of patients     
{int} S = ...;   //Set of surgeons

// Surgery Types
{int} SurgeryTypes = ...; 

//Parameters
float wh = ...;       

// 1 if surgeon s is qualified for surgery type t, 0 otherwise
int IsResponsible[S][SurgeryTypes] = ...;
int IsAssistant1[S][SurgeryTypes] = ...;
int IsAssistant2[S] = ...; // applied to all surgery types

// Duration 
float DurationByType[SurgeryTypes] = ...; 
int PatientType[P] = ...;
float tp[p in P] = DurationByType[PatientType[p]];

// Resting Time
float RestingTimeByType[SurgeryTypes] = ...;
float Rsp[s in S, p in P] = RestingTimeByType[PatientType[p]];

float BigM = 10000;   

// Decision variables
dvar boolean xsp[S,P];      
dvar boolean wsp[S,P];      
dvar boolean ysp[S,P];      
dvar boolean zsp[S,P];      
dvar boolean rspp[S,P,P]; 
dvar boolean fssp[S,S,P]; 
dvar float+ startsp[S,P];   
dvar float+ Us[S];          
dvar float+ Umax;           

//Objective function (1)
minimize Umax;

//Constraints
subject to {
// (2) Each patient must be assigned exactly ONE Responsible Surgeon
  forall(p in P)
    sum(s in S) wsp[s,p] == 1;

 //Each patient must be assigned exactly ONE First Assistant
  forall(p in P)
    sum(s in S) ysp[s,p] == 1;

 //Each patient must be assigned exactly ONE Second Assistant
  forall(p in P)
    sum(s in S) zsp[s,p] == 1;
  
  // Responsible Surgeon Qualification
  forall(p in P, s in S) {
    wsp[s,p] <= IsResponsible[s][PatientType[p]];
  }

  // 1st Assistant Qualification
  forall(p in P, s in S) {
    ysp[s,p] <= IsAssistant1[s][PatientType[p]];
  }

  // 2nd Assistant Qualification
  forall(p in P, s in S) {
    zsp[s,p] <= IsAssistant2[s];
  }

 // (3) & (4) Link roles to the assignment variable (x_sp)
  forall(s in S, p in P) {
  	xsp[s,p] <= wsp[s,p] + ysp[s,p] + zsp[s,p];
    xsp[s,p] >= wsp[s,p] + ysp[s,p] + zsp[s,p];
  }

  // (5) Precedence constraint: p and p2 cannot both be before each other
  forall(s in S, p in P, p2 in P : p != p2) 
    rspp[s,p,p2] + rspp[s,p2,p] <= 1;

  // (6) & (7) Sequencing constraints based on assignment
  // If surgeon s operates on both p and p2, a precedence relationship must exist
  forall(s in S, p in P, p2 in P : p != p2) {
    xsp[s,p] + xsp[s,p2] >= 2 * (rspp[s,p,p2] + rspp[s,p2,p]);
    xsp[s,p] + xsp[s,p2] <= 1 + (rspp[s,p,p2] + rspp[s,p2,p]);
  }

  // (8) Start time constraint based on sequence
  // If p is before p2, start time of p2 must be >= start time of p + duration + rest
  forall(s in S, p in P, p2 in P : p != p2)
    startsp[s,p2] >= startsp[s,p] + rspp[s,p,p2]*(tp[p] + Rsp[s,p]) - BigM * (1 - rspp[s,p,p2]);

  // (9) & (10) Define the team variable (f_ss'p)
  // f_ss'p = 1 if both surgeon s and s2 are assigned to patient p
  forall(s in S, s2 in S : s != s2, p in P) {
    xsp[s,p] + xsp[s2,p] >= 2 * fssp[s,s2,p];
    xsp[s,p] + xsp[s2,p] <= 1 + fssp[s,s2,p];
  }

  // (11) & (12) Synchronize start times for surgeons in the same team
  // If s and s2 work together, their start times must be equal
  forall(s in S, s2 in S : s != s2, p in P) {
    startsp[s,p] >= startsp[s2,p] - wh * (1 - fssp[s,s2,p]);
    startsp[s,p] <= startsp[s2,p] + wh * (1 - fssp[s,s2,p]);
  }

  // (13) Daily working hours constraint
  // Completion time (start + duration + rest) must not exceed daily limit (wh)
  forall(s in S, p in P)
    wh >= startsp[s,p] + xsp[s,p] * (Rsp[s,p] + tp[p]);

  // [ADDING] Force start time to 0 if not assigned (for cleaner results)
  forall(s in S, p in P)
    startsp[s,p] <= BigM * xsp[s,p];

  // (14) Calculate Unproductive Time (Us) for each surgeon
  // Us = Total Hours - Total Working Time (duration + rest)
  forall(s in S)
    Us[s] == wh - sum(p in P) ( xsp[s,p] * (tp[p] + Rsp[s,p]) );

  // (17) Define Umax (Minimax objective)
  // Umax must be greater than or equal to the unproductive time of any surgeon
  forall(s in S)
    Umax >= Us[s];

}