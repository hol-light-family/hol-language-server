(* HOL constants used inside backquoted terms.
   Checked: in a term, Go to Definition and hover on a constant go to the
   definition that introduces it, made with define, new_definition (also an
   infix), new_recursive_definition, or new_inductive_definition, or in
   hol.ml (EVEN). A variable in a term goes nowhere, even when an OCaml value
   has its name (n). `^x_term` is the OCaml value x_term. *)

let n = 5;;

let fibonacci = define
 `fibonacci 0 = 0 /\ fibonacci 1 = 1 /\
  fibonacci (n + 2) = fibonacci n + fibonacci (n + 1)`;;

(* goto: fibonacci n + => fibonacci 0 = 0 *)
(* goto: fibonacci (n + 2) +11 => nowhere *)

let FIB_DEF = new_definition `fib n = fibonacci n`;;

(* hover: fib n = +4 => none *)

let FIB3 = new_recursive_definition num_RECURSION
  `fib3 0 = 0 /\ fib3 (SUC n) = fib3 n + 1`;;

parse_as_infix("divides_alt",(12,"right"));;

let DIVIDES_ALT = new_definition `m divides_alt n <=> ?x. n = m * x`;;

let EVENS_RULES, EVENS_INDUCT, EVENS_CASES = new_inductive_definition
  `evens 0 /\ (!n. evens n ==> evens (n + 2))`;;

let FIB_1 = prove
 (`fib 1 = 1 /\ fib3 1 = 1`,
  REWRITE_TAC[FIB_DEF; fibonacci]);;

(* goto: fib 1 = 1 => fib n = fibonacci *)
(* goto: fib3 1 = 1 => fib3 0 = 0 *)
(* goto: FIB_DEF; => FIB_DEF = *)
(* goto: fibonacci] => fibonacci = define *)
(* hover: fib 1 = 1 =>
Constant `fib`, defined by `FIB_DEF`
```
`|- fib n = fibonacci n`
``` *)

let x_term = `x:num`;;

let USES = `2 divides_alt 4 /\ evens 4 /\ EVEN 4 /\ fib ^x_term = 1`;;

(* goto: divides_alt 4 => divides_alt n <=> *)
(* goto: evens 4 => evens 0 /\ *)
(* goto: EVEN 4 => EVEN n <=> @hol/hol.ml *)
(* goto: fib ^x_term +5 => x_term = *)
