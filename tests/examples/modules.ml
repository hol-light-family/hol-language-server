(* Module structure: nested modules, `open`, `include`, a signature, a module
   type, and a functor (Make).
   Checked: the definitions and modules in the `expect` comments, how the
   modules nest, and the position of the top-level `open Utils`. newMap1 and
   exists1 follow a `type` item that is not ended by `;;`, and must still be
   found. `Subst` (a functor application) and `Ordered` (a module type) are
   not modules. *)

(* Examples from metis.ml, firstorder.ml, thecops.ml *)

module Utils = struct
let const x _ = x

module Pair =
struct
    
let mapn f (x, y) = (f x, f y)
    
end

open Pair

module List =
struct
    
    include List
        
    let cons x l = begin 
        x :: l 
    end

end

module Subst = Substoff (Substarray)

module Substlist : Substitution with type t = (int * iterm) list =
    struct

    exception Unify
    open Utils.Pair

    type t = (int * iterm) list

    end

end
(* expect: Utils.const Utils.Pair.mapn Utils.List.cons *)
(* expect module: Utils Utils.Pair Utils.List Utils.Substlist *)

let test_expr = 1;;
let expr =;;
(* expect: test_expr expr *)

open Utils;;

module Mmap = struct

    exception Error = Useful.Error;;
    
    module type Ordered =
    sig
        type t
        val compare1 : t -> t -> int
    end

    module Make (Ord : Ordered) =
    struct
        module Ma = Map.Make (Ord)

        type +'a map = 'a Ma.t

        let newMap1 () = Ma.empty;;
        let exists1 f = Ma.exists (fun k m -> f (k,m));;
    end
end
(* expect: Mmap.Make.newMap1 Mmap.Make.exists1 *)
(* expect module: Mmap Mmap.Make *)