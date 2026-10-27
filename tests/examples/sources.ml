(* Where the source of each definition starts and ends: the whole item
   that defines it, from its `let` to its `;;`.
   - One line, several lines, and a theorem over several lines.
   - `let ... and ...`: every name gets the whole item.
   - An item not ended by `;;`: it ends before the next `let`.
   - A comment before `;;` and trailing spaces after it.
   - An indented item inside a module. *)

let one = 1;;
(* expect: one@9:1-9:13 *)

let two x =
  x + 1;;
(* expect: two@12:1-13:9 *)

let TH = prove
 (`x = x`,
  REFL_TAC);;
(* expect: TH:theorem@16:1-18:13 *)

let a = 1
and b = 2;;
(* expect: a@21:1-22:11 b@21:1-22:11 *)

let no_sep = 1
let next = 2;;
(* expect: no_sep@25:1-25:14 next@26:1-26:14 *)

let c = 3 (* a comment *) ;;
(* expect: c@29:1-29:28 *)

module M = struct
  let inner = 1;;
end;;
(* expect: M.inner@33:3-33:17 *)
(* expect module: M *)
