(* Defines M.Inner, and opens M for the files loaded after it. *)

module M = struct
  module Inner = struct
    let treasure = 1
  end
end;;

open M;;
