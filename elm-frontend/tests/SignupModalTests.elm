module SignupModalTests exposing (suite)

import Expect
import Json.Decode as Decode
import SignupModal exposing (State, StatusMsg(..))
import Test exposing (Test, describe, test)


base : State
base =
    { open = False, email = "a@b.co", statusMsg = Idle }


suite : Test
suite =
    describe "SignupModal"
        [ test "openModal opens and keeps email and status" <|
            \_ ->
                SignupModal.openModal { base | statusMsg = Error "x" }
                    |> Expect.equal { open = True, email = "a@b.co", statusMsg = Error "x" }
        , test "closeModal resets Error to Idle" <|
            \_ ->
                SignupModal.closeModal { base | open = True, statusMsg = Error "x" }
                    |> Expect.equal { open = False, email = "a@b.co", statusMsg = Idle }
        , test "closeModal resets Sent to Idle" <|
            \_ ->
                SignupModal.closeModal { base | open = True, statusMsg = Sent "ok" }
                    |> .statusMsg
                    |> Expect.equal Idle
        , test "closeModal leaves Sending unchanged" <|
            \_ ->
                SignupModal.closeModal { base | open = True, statusMsg = Sending }
                    |> Expect.equal { open = False, email = "a@b.co", statusMsg = Sending }
        , test "closeModal after Sent clears email" <|
            \_ ->
                SignupModal.closeModal { base | open = True, statusMsg = Sent "ok" }
                    |> .email
                    |> Expect.equal ""
        , test "closeModal after Error keeps email" <|
            \_ ->
                SignupModal.closeModal { base | open = True, statusMsg = Error "x" }
                    |> .email
                    |> Expect.equal "a@b.co"
        , test "onSubscribeResult True sends and clears email" <|
            \_ ->
                SignupModal.onSubscribeResult True { base | statusMsg = Sending }
                    |> Expect.equal
                        { open = False
                        , email = ""
                        , statusMsg = Sent "Check your email to confirm!"
                        }
        , test "onSubscribeResult False errors and keeps email" <|
            \_ ->
                SignupModal.onSubscribeResult False { base | statusMsg = Sending }
                    |> Expect.equal
                        { open = False
                        , email = "a@b.co"
                        , statusMsg = Error "Failed to subscribe."
                        }
        , test "escapeDecoder accepts Escape" <|
            \_ ->
                Decode.decodeString (SignupModal.escapeDecoder ()) "{\"key\":\"Escape\"}"
                    |> Expect.equal (Ok ())
        , test "escapeDecoder rejects Enter" <|
            \_ ->
                Decode.decodeString (SignupModal.escapeDecoder ()) "{\"key\":\"Enter\"}"
                    |> Expect.err
        , test "enterDecoder accepts Enter only" <|
            \_ ->
                ( Decode.decodeString (SignupModal.enterDecoder ()) "{\"key\":\"Enter\"}"
                , Decode.decodeString (SignupModal.enterDecoder ()) "{\"key\":\"a\"}"
                )
                    |> Tuple.mapBoth (\r -> r == Ok ()) (\r -> r /= Ok ())
                    |> Expect.equal ( True, True )
        ]
