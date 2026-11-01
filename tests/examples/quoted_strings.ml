(* OCaml quoted strings hold anything: nothing in them starts a comment, a
   string, a term, a load, or a definition, and definitions after them are found.
   Checked: the definitions and modules in the expect comments. Loads are
   checked in test_core.py. *)

let a = {|text (* not a comment|};;
let after_a = 1;;
(* expect: a after_a *)

let b = {|it"s|};;
let after_b = 1;;
(* expect: b after_b *)

let c = {|a `b|};;
let after_c = 1;;
(* expect: c after_c *)

let d = {id|x |} y|id};;
let after_d = 1;;
(* expect: d after_d *)

let e = {|
let ghost = 1;;
module Ghost = struct let ghost2 = 1 end;;
|};;
let after_e = 1;;
(* expect: e after_e *)

(* Not closed by a closing with another id. *)
let f = {a|x|b} y|a};;
let after_f = 1;;
(* expect: f after_f *)

(* Skipped past when the item is not ended by a ;; *)
let g = 1
let h = {|;; let ghost3 = 1;;
|}
let after_h = 1;;
(* expect: g h after_h *)

(* Braces that are not quoted strings. *)
let i = {x = 1};;
let after_i = 1;;
(* expect: i after_i *)
