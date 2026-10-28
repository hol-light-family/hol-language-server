(* Comment definitions are not definitions.
   - `shadowed` is defined below for real; the commented one must not win.
   - `ghost` is defined only in a comment; uses of it go nowhere. *)

(* let shadowed = 1;; *)
let shadowed = 2;;

let uses = shadowed + ghost;;

(* goto: = shadowed + +2 => let shadowed = 2 +4 *)
(* goto: + ghost +2 => nowhere *)
(* hover: + ghost +2 => none *)
