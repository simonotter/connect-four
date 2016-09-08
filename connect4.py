import endpoints
from protorpc import remote, messages
from models import User, Game
from models import StringMessage, NewGameForm, GameForm, MakeMoveForm
from utils import get_by_urlsafe

API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
EMAIL_SCOPE = endpoints.EMAIL_SCOPE

USER_REQUEST = endpoints.ResourceContainer(user_name=messages.StringField(1),
                                           email=messages.StringField(2))
NEW_GAME_REQUEST = endpoints.ResourceContainer(NewGameForm)
GET_GAME_REQUEST = endpoints.ResourceContainer(
    urlsafe_game_key=messages.StringField(1), )
MAKE_MOVE_REQUEST = endpoints.ResourceContainer(
    MakeMoveForm,
    urlsafe_game_key=messages.StringField(1), )


@endpoints.api(name='connect4',
               version='v1',
               allowed_client_ids=[API_EXPLORER_CLIENT_ID],
               scopes=[EMAIL_SCOPE])
class ConnectFourApi(remote.Service):
    """Connect Four API v0.1"""

    @endpoints.method(request_message=USER_REQUEST,
                      response_message=StringMessage,
                      path='user',
                      name='create_user',
                      http_method='POST')
    def create_user(self, request):
        """Create a User. Requires a unique username"""
        if User.query(User.name == request.user_name).get():
            raise endpoints.ConflictException(
                'A User with that name already exists!')
        user = User(name=request.user_name, email=request.email)
        user.put()
        return StringMessage(message='User {} created!'.format(
            request.user_name))

    @endpoints.method(request_message=NEW_GAME_REQUEST,
                      response_message=GameForm,
                      path='game',
                      name='new_game',
                      http_method='POST')
    def new_game(self, request):
        """Creates a new Game"""
        try:
            game = Game.new_game(request.player1, request.player2)
        except ValueError:
            raise endpoints.BadRequestException('Invalid player objects')

        return game.to_form(
            "Good luck. It\'s %s\'s turn" % game.whose_turn.get().name)

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='get_game',
                      http_method='GET')
    def get_game(self, request):
        """Return the current game state."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            if game.game_over:
                return game.to_form('This game has ended. It was won by %s.'
                                    % game.whose_turn.get().name)
            else:
                return game.to_form(
                    'Time to make a move, %s!' % game.whose_turn.get().name)
        else:
            raise endpoints.NotFoundException('Game not found!')

    @endpoints.method(request_message=MAKE_MOVE_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='make_move',
                      http_method='PUT')
    def make_move(self, request):
        """Makes a move. Returns a game state with message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if not game:
            """ TODO: Udacity Reviewer, how can I return a null GameForm
                      response if the game doesn't exist?"""
            raise ValueError("Game doesn't exist")

        if game.game_over:
            return game.to_form('This game has ended. It was won by %s.'
                                % game.whose_turn.get().name)

        # TODO: Check if integer
        column = int(request.column)
        # validate the column input
        if not (1 <= column <= 7):
            return game.to_form('Column must be a number between 1 and 7!')

        """ TODO: Udacity Reviewer, is this efficient to keep getting the
                  names each time? I seem to be doing it all the time in this
                  method and it will make many reads to the ndb"""

        # Check if the player is part of this game
        if request.player not in [game.player1.get().name,
                                  game.player2.get().name]:
            return game.to_form('You are not part of this game')

        # Ensure it's this players turn
        if game.whose_turn.get().name != request.player:
            return game.to_form(
                "It's not your turn, it's %s's!" % game.whose_turn.get().name)

        # Get token colour of current player
        if request.player == game.player1.get().name:
            colour = game.player1Colour
        else:
            colour = game.player2Colour

        if game.board.update(column, colour):

            # Decrease attempts remaining
            game.holes_remaining -= 1

            # Check if game has been won
            if game.is_won():
                game.game_over = True
                message = "%s has won the game!" % game.whose_turn.get().name
            else:
                # Update whose_turn to next player
                game.switch_turn()
                message = "Now it's %s's turn." % game.whose_turn.get().name

            # Store the updated game in ndb
            game.put()

        else:
            message = "This column is full, try another column"

        return game.to_form(message)


# registers API
api = endpoints.api_server([ConnectFourApi])