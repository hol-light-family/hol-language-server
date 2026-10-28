(* A variable a term binds hides a constant of its name.
   Cut down from s2n-bignum arm/proofs/edwards25519_epadd.ml, where
   `!p3 p1 Q1 p2 Q2 pc stackpointer.` binds the names of two registers.
   Checked: Go to Definition and hover on a bound Q1 go nowhere; a Q1
   outside any binder body jumps to the constant. *)

let Q1 = define `Q1 = 1`;;

let TH = prove(`!Q1. Q1 = 2`, ALL_TAC);;

(* goto: Q1 = 2 => nowhere *)
(* goto: Q1. Q1 = 2 => nowhere *)
(* hover: Q1 = 2 => none *)

let SCOPED = `(!Q1. Q1 = 3) /\ Q1 = 4`;;

(* goto: Q1 = 3 => nowhere *)
(* goto: Q1 = 4 => Q1 = 1 *)

let OTHERS = `(?!Q1:num. Q1 = 5) /\ (\Q1. Q1 + 6) = f /\ [!(Q1:24 word). Q1 = 7; Q1 = 8]`;;

(* goto: Q1 = 5 => nowhere *)
(* goto: Q1 + 6 => nowhere *)
(* goto: Q1 = 7 => nowhere *)
(* goto: Q1 = 8 => Q1 = 1 *)

let CONJ = `x /\ Q1 = 9 \/ Q1 = 10`;;

(* goto: Q1 = 9 => Q1 = 1 *)
(* goto: Q1 = 10 => Q1 = 1 *)
