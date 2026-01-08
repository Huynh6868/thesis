/*********************************************
 * OPL 12.9.0.0 Model
 * Author: ASUS
 * Creation Date: Dec 9, 2025 at 9:49:31 PM
 *********************************************/
/****************************************************
 * Phase 1: Surgical Team Assignment Problem
 ****************************************************/
//need to fix: 
//1. add eligible set data and logic
//2. Check the shift of surgeon. 
//3. check the time horizontal of this code 


/*** Sets ***/
{int} P = ...;        // Set of patients IDs
{int} S = ...;        // Set of surgeons IDs

/*** Parameters ***/
float wh = ...;       // Daily working hours (e.g., 480 minutes or 8 hours)
float tp[P] = ...;    // Duration of operation for patient p
float Rsp[S,P] = ...; // Resting time matrix

// BigM 
float BigM = 10000;   

//eligibility
//wsp[S,P] <= canResp[S,P];
//ysp[S,P] <= canFA[S,P];
//zsp[S,P] <= canSA[S,P];

/*** Decision variables ***/
dvar boolean xsp[S,P];      // 1 if surgeon s is assigned to patient p
dvar boolean wsp[S,P];      // 1 if surgeon s is Responsible
dvar boolean ysp[S,P];      // 1 if surgeon s is 1st Assistant
dvar boolean zsp[S,P];      // 1 if surgeon s is 2nd Assistant

// Precedence variable: p' comes after p for surgeon s
dvar boolean rspp[S,P,P]; 

// Team variable: s and s' work together on p
dvar boolean fssp[S,S,P]; 

dvar float+ startsp[S,P];   // Start time
dvar float+ Us[S];          // Unproductive time per surgeon
dvar float+ Umax;           // Minimax objective

/*** Objective function ***/
minimize Umax;

/*** Constraints ***/
subject to {

  // (2) each patient has 1 main surgeon
  forall(p in P) sum(s in S) wsp[s,p] == 1;

  // each patient has 1 a1 surgeon
  forall(p in P) sum(s in S) ysp[s,p] == 1;
  
  // each patient has 1 a2 surgeon
  forall(p in P) sum(s in S) zsp[s,p] == 1;

  // (3) & (4) 
  // 1 surgeon - 1 role
  forall(s in S, p in P) {
    xsp[s,p] <= wsp[s,p] + ysp[s,p] + zsp[s,p];
    xsp[s,p] >= wsp[s,p] + ysp[s,p] + zsp[s,p];
  }

  // (5) 
  forall(s in S, p in P, p2 in P : p != p2)
    rspp[s,p,p2] + rspp[s,p2,p] <= 1;

  // (6) & (7) if s is responsible for p and p' -> 1 case is operated before the other
  forall(s in S, p in P, p2 in P : p != p2) {
    xsp[s,p] + xsp[s,p2] >= 2 * (rspp[s,p,p2] + rspp[s,p2,p]);
    
    xsp[s,p] + xsp[s,p2] <= 1 + (rspp[s,p,p2] + rspp[s,p2,p]);
  }

  // (8) 
  forall(s in S, p in P, p2 in P : p != p2)
    startsp[s,p2] >= startsp[s,p] + tp[p] + Rsp[s,p] - BigM * (1 - rspp[s,p,p2]);                

  // (9) & (10) 
  forall(s in S, s2 in S : s != s2, p in P) {
    xsp[s,p] + xsp[s2,p] >= 2 * fssp[s,s2,p];

    xsp[s,p] + xsp[s2,p] <= 1 + fssp[s,s2,p];
  }

  // (11) & (12) if they are in the same team -> same start time. 
  forall(s in S, s2 in S : s != s2, p in P) {
    startsp[s,p] >= startsp[s2,p] - wh * (1 - fssp[s,s2,p]);
 
    startsp[s,p] <= startsp[s2,p] + wh * (1 - fssp[s,s2,p]);
  }

  // (13) limit working time per day (Working Hours)
  forall(s in S, p in P)
    wh >= startsp[s,p] + xsp[s,p] * (Rsp[s,p] + tp[p]);

  // [CLEAN UP] if s dont operate p => start time = 0 
  forall(s in S, p in P)
    startsp[s,p] <= BigM * xsp[s,p];

  // (14) calculate unproductive time
  forall(s in S)
    Us[s] == wh - sum(p in P) ( xsp[s,p] * (tp[p] + Rsp[s,p]) );

  // (17) Minimax Objective
  forall(s in S)
    ct17_Minimax:
    Umax >= Us[s];

}