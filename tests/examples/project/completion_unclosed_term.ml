(* Term completion without the closing backquote.
   Loads constants.ml for fib3. The unclosed term must stay the last thing
   in the file: any backquote below it would pair with its opening one.
   Checked: the label and kind in the `complete` comment. *)

needs "constants.ml";;

let UNCLOSED = `fib3
(* complete: UNCLOSED = +6 => fib3:constant *)
