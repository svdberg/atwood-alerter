module SignupModal exposing
    ( State
    , StatusMsg(..)
    , closeModal
    , enterDecoder
    , errorMessage
    , escapeDecoder
    , networkErrorMessage
    , onEmailChange
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


fallbackErrorMessage : String
fallbackErrorMessage =
    "Failed to subscribe. Please try again."


networkErrorMessage : String
networkErrorMessage =
    "Couldn't reach the server. Check your connection and try again."


{-| Extract the `error` field from a failed /subscribe response body.
-}
errorMessage : String -> Maybe String
errorMessage body =
    case Decode.decodeString (Decode.field "error" Decode.string) body of
        Ok "" ->
            Nothing

        Ok msg ->
            Just msg

        Err _ ->
            Nothing


onSubscribeResult : Result (Maybe String) () -> State -> State
onSubscribeResult result state =
    case result of
        Ok () ->
            { state | statusMsg = Sent "Check your email to confirm!", email = "" }

        Err (Just msg) ->
            { state | statusMsg = Error msg }

        Err Nothing ->
            { state | statusMsg = Error fallbackErrorMessage }


{-| Editing the email clears a stale error, but not Sent or Sending.
-}
onEmailChange : String -> State -> State
onEmailChange val state =
    case state.statusMsg of
        Error _ ->
            { state | email = val, statusMsg = Idle }

        _ ->
            { state | email = val }


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
