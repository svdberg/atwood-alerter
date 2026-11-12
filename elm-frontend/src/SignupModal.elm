module SignupModal exposing
    ( State
    , StatusMsg(..)
    , closeModal
    , enterDecoder
    , escapeDecoder
    , onSubscribeResult
    , openModal
    )

import Json.Decode as Decode exposing (Decoder)


type StatusMsg
    = Idle
    | Sending
    | Sent String
    | Error String


type alias State =
    { open : Bool
    , email : String
    , statusMsg : StatusMsg
    }


openModal : State -> State
openModal state =
    { state | open = True }


closeModal : State -> State
closeModal state =
    case state.statusMsg of
        Sending ->
            { state | open = False }

        Sent _ ->
            { state | open = False, email = "", statusMsg = Idle }

        Error _ ->
            { state | open = False, statusMsg = Idle }

        Idle ->
            { state | open = False }


onSubscribeResult : Bool -> State -> State
onSubscribeResult ok state =
    if ok then
        { state | statusMsg = Sent "Check your email to confirm!", email = "" }

    else
        { state | statusMsg = Error "Failed to subscribe." }


keyDecoder : String -> msg -> Decoder msg
keyDecoder expected msg =
    Decode.field "key" Decode.string
        |> Decode.andThen
            (\key ->
                if key == expected then
                    Decode.succeed msg

                else
                    Decode.fail ("ignored key: " ++ key)
            )


escapeDecoder : msg -> Decoder msg
escapeDecoder =
    keyDecoder "Escape"


enterDecoder : msg -> Decoder msg
enterDecoder =
    keyDecoder "Enter"
